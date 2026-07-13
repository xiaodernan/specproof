"""Capability Probe — validates an OpenAI-compatible gateway before use.

Runs 10 atomic checks. Results written to MySQL provider_capabilities
and cached in Redis (TTL 86400s).

Usage:
    probe = CapabilityProbe(base_url="https://provider.example/v1",
                            api_key="...", model="deepseek-v4-pro")
    result = await probe.run()
    print(result.summary())
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .probe_result import ProbeResult


class CapabilityProbe:
    """Validates an OpenAI-compatible gateway endpoint.

    Probe items (10 total):
    1. GET /models          — endpoint reachable, model list non-empty
    2. Chat                 — single-turn completion returns content
    3. Streaming            — stream=True delivers chunk stream
    4. JSON Output          — response_format={"type":"json_object"} parseable
    5. Tool Calls           — single tool definition returns tool_calls
    6. Strict Tool Calls    — tool_choice="required" enforced
    7. Thinking             — extra_body thinking enabled → reasoning_content
    8. Thinking + Tool      — thinking enabled + tools coexist
    9. Usage                — usage.prompt_tokens/completion_tokens non-zero
    10. Error + Rate Limit  — bad request → HTTP error + x-ratelimit-* headers
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._redacted_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def run(self) -> ProbeResult:
        capabilities: dict[str, bool] = {}
        limits: dict[str, Any] = {}
        errors: list[str] = []

        checks = [
            ("chat", self._check_chat),
            ("streaming", self._check_streaming),
            ("json_output", self._check_json_output),
            ("tool_calls", self._check_tool_calls),
            ("strict_tool_calls", self._check_strict_tool_calls),
            ("thinking", self._check_thinking),
            ("thinking_with_tools", self._check_thinking_with_tools),
            ("usage_reporting", self._check_usage),
            ("error_codes", self._check_error_codes),
            ("rate_limit_headers", self._check_rate_limit_headers),
        ]

        # 1. Check /models first — gateway must be reachable
        reachable, model_list, err = await self._check_models()
        if not reachable:
            errors.append(f"Gateway unreachable: {err}")
            for name, _fn in checks:
                capabilities[name] = False
            return ProbeResult(
                provider="openai_compatible",
                base_url=self.base_url,
                model=self.model,
                capabilities=capabilities,
                limits=limits,
                errors=errors,
            )

        # 2. Run each check sequentially
        for name, check_fn in checks:
            try:
                passed, detail = await check_fn()
                capabilities[name] = passed
                if not passed:
                    errors.append(f"{name}: {detail}")
            except Exception as exc:
                capabilities[name] = False
                errors.append(f"{name}: {exc}")

        return ProbeResult(
            provider="openai_compatible",
            base_url=self.base_url,
            model=self.model,
            capabilities=capabilities,
            limits=limits,
            errors=errors,
        )

    # ── Individual checks ──────────────────────────────────────────

    async def _check_models(self) -> tuple[bool, list[str], str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
            if resp.status_code != 200:
                return False, [], f"HTTP {resp.status_code}"
            data = resp.json()
            models = [m.get("id", "") for m in data.get("data", [])]
            return len(models) > 0, models, ""
        except Exception as e:
            return False, [], str(e)

    async def _check_chat(self) -> tuple[bool, str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Reply with just: ok"}],
            "max_tokens": 200,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            content = data["choices"][0]["message"].get("content", "")
            return bool(content), ""
        except Exception as e:
            return False, str(e)

    async def _check_streaming(self) -> tuple[bool, str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Say hello"}],
            "stream": True,
            "max_tokens": 10,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                chunks = 0
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        return False, f"HTTP {response.status_code}"
                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            chunks += 1
                return chunks > 0, f"received {chunks} chunks"
        except Exception as e:
            return False, str(e)

    async def _check_json_output(self) -> tuple[bool, str]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": 'Return JSON: {"key": "value"}',
                }
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 500,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            content = data["choices"][0]["message"].get("content", "")
            json.loads(content)
            return True, ""
        except (json.JSONDecodeError, Exception) as e:
            return False, str(e)

    async def _check_tool_calls(self) -> tuple[bool, str]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ]
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
            "tools": tools,
            "max_tokens": 50,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls", [])
            return len(tool_calls) > 0, ""
        except Exception as e:
            return False, str(e)

    async def _check_strict_tool_calls(self) -> tuple[bool, str]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "Get current time",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
        ]
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "What time is it?"}],
            "tools": tools,
            "tool_choice": "required",
            "max_tokens": 50,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls", [])
            return len(tool_calls) > 0, "tool_choice=required resulted in no tool call"
        except Exception as e:
            return False, str(e)

    async def _check_thinking(self) -> tuple[bool, str]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Think step by step: what is 17 * 24?",
                }
            ],
            "max_tokens": 200,
        }
        payload_with_thinking = {
            **payload,
            "extra_body": {"thinking": {"type": "enabled"}},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload_with_thinking,
                )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            msg = data["choices"][0]["message"]
            reasoning = msg.get("reasoning_content") or data["choices"][0].get(
                "reasoning_content", ""
            )
            return bool(reasoning), "no reasoning_content in response"
        except Exception as e:
            return False, str(e)

    async def _check_thinking_with_tools(self) -> tuple[bool, str]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Calculate an expression",
                    "parameters": {
                        "type": "object",
                        "properties": {"expression": {"type": "string"}},
                        "required": ["expression"],
                    },
                },
            }
        ]
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Think before you calculate: 15 * 8",
                }
            ],
            "tools": tools,
            "max_tokens": 200,
            "extra_body": {"thinking": {"type": "enabled"}},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            msg = data["choices"][0]["message"]
            reasoning = msg.get("reasoning_content") or data["choices"][0].get(
                "reasoning_content", ""
            )
            tool_calls = msg.get("tool_calls", [])
            return (
                bool(reasoning) and len(tool_calls) > 0
            ), f"reasoning={bool(reasoning)}, tool_calls={len(tool_calls)}"
        except Exception as e:
            return False, str(e)

    async def _check_usage(self) -> tuple[bool, str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 10,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            data = resp.json()
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            return (
                prompt_tokens > 0 and completion_tokens > 0
            ), f"prompt={prompt_tokens}, completion={completion_tokens}"
        except Exception as e:
            return False, str(e)

    async def _check_error_codes(self) -> tuple[bool, str]:
        """Send a bad request and verify structured error response."""
        payload = {
            "model": "nonexistent-model-zzz",
            "messages": [{"role": "user", "content": "test"}],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            # Expecting 4xx/5xx
            data = resp.json() if resp.text else {}
            has_error = "error" in data or resp.status_code >= 400
            return has_error, f"status={resp.status_code}"
        except Exception as e:
            return False, str(e)

    async def _check_rate_limit_headers(self) -> tuple[bool, str]:
        """Check for x-ratelimit-* headers in response."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            rate_limit_headers = {
                k: v for k, v in resp.headers.items() if k.lower().startswith("x-ratelimit")
            }
            return len(rate_limit_headers) > 0, f"found {len(rate_limit_headers)} headers"
        except Exception as e:
            return False, str(e)
