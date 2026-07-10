"""OpenAICompatibleProvider — ModelProvider backed by any /v1 endpoint.

This is the primary LLM provider for Phase 0.
It uses the openai SDK with a custom base_url.
Capabilities are probed before first use.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from .base import LLMMessage, LLMResponse, ModelProvider
from .capability_probe import CapabilityProbe
from .probe_result import ProbeResult


def _redact_key(key: str) -> str:
    if len(key) <= 12:
        return "***"
    return key[:8] + "..." + key[-4:]


class OpenAICompatibleProvider(ModelProvider):
    """OpenAI-compatible provider with capability probing and degradation."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
        probe_on_init: bool = False,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-v4-pro")
        self.timeout = timeout
        self._probe_result: ProbeResult | None = None
        self._client: AsyncOpenAI | None = None

        if not self.api_key or self.api_key == "replace_me":
            raise ValueError(
                "LLM_API_KEY is not set or is placeholder 'replace_me'. "
                "Set the environment variable or pass api_key explicitly."
            )

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            base_url_value = self.base_url
            if not base_url_value.endswith("/v1"):
                base_url_value += "/v1"
            self._client = AsyncOpenAI(
                base_url=base_url_value,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=2,
            )
        return self._client

    @property
    def probe_result(self) -> ProbeResult:
        if self._probe_result is None:
            raise RuntimeError(
                "Provider not probed. Call run_probe() before get_capabilities()."
            )
        return self._probe_result

    async def run_probe(self) -> ProbeResult:
        probe = CapabilityProbe(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
        )
        self._probe_result = await probe.run()
        return self._probe_result

    def get_capabilities(self) -> dict:
        return self.probe_result.capabilities

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
        thinking: bool = False,
        timeout: float = 180.0,
    ) -> LLMResponse:
        caps = self.get_capabilities()

        oai_messages = self._to_openai_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "timeout": timeout,
        }
        if tools and caps.get("tool_calls", False):
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
        elif tools and not caps.get("tool_calls", False):
            kwargs["messages"] = self._inject_tool_prompt(oai_messages, tools)

        if response_format and caps.get("json_output", False):
            kwargs["response_format"] = response_format

        extra_body: dict[str, Any] = {}
        if thinking and caps.get("thinking", False):
            extra_body["thinking"] = {"type": "enabled"}
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = await self.client.chat.completions.create(**kwargs)
        return self._to_llm_response(response)

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        thinking: bool = False,
        timeout: float = 180.0,
    ) -> AsyncIterator[LLMResponse]:
        caps = self.get_capabilities()

        oai_messages = self._to_openai_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "stream": True,
            "timeout": timeout,
        }
        if tools and caps.get("tool_calls", False):
            kwargs["tools"] = tools
        elif tools:
            kwargs["messages"] = self._inject_tool_prompt(oai_messages, tools)

        extra_body: dict[str, Any] = {}
        if thinking and caps.get("thinking", False):
            extra_body["thinking"] = {"type": "enabled"}
        if extra_body:
            kwargs["extra_body"] = extra_body

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                yield LLMResponse(
                    content=delta.content,
                    tool_calls=(
                        [
                            {
                                "id": tc.id,
                                "function": {
                                    "name": tc.function.name if tc.function else "",
                                    "arguments": tc.function.arguments if tc.function else "",
                                },
                            }
                            for tc in delta.tool_calls
                        ]
                        if delta.tool_calls
                        else []
                    ),
                    model=chunk.model or self.model,
                    finish_reason=chunk.choices[0].finish_reason or "",
                )

    # ── Private helpers ────────────────────────────────────────────

    def _to_openai_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for m in messages:
            msg: dict[str, Any] = {"role": m.role}
            if m.content is not None:
                msg["content"] = m.content
            if m.tool_call_id is not None:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls is not None:
                msg["tool_calls"] = m.tool_calls
            result.append(msg)
        return result

    def _to_llm_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        return LLMResponse(
            content=msg.content,
            tool_calls=(
                [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
                if msg.tool_calls
                else []
            ),
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            finish_reason=choice.finish_reason or "stop",
            model=response.model,
        )

    def _inject_tool_prompt(
        self, messages: list[dict[str, Any]], tools: list[dict]
    ) -> list[dict[str, Any]]:
        """Degrade: inject tool definitions as system prompt."""
        tool_desc = json.dumps(tools, indent=2)
        system_msg = {
            "role": "system",
            "content": (
                "You have access to the following tools. "
                "Respond with a JSON action envelope: "
                '{"action": "tool_name", "params": {...}}\n\n'
                f"Tools:\n{tool_desc}"
            ),
        }
        return [system_msg] + messages

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
