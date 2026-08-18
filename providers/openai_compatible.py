"""OpenAICompatibleProvider — ModelProvider backed by any /v1 endpoint.

This is the primary LLM provider for Phase 0.
It uses the openai SDK with a custom base_url.
Capabilities are probed before first use.

DeepSeek V4 Pro adaptation (see docs/design/DEEPSEEK_V4_PRO_ADAPTATION.md):
- usage parsing reads prompt_cache_hit_tokens / prompt_cache_miss_tokens
  and reasoning tokens by their actual field names; missing fields are
  honestly skipped, never fabricated;
- 429 rate limits are retried with tenacity using the gateway's
  Retry-After header, bounded by LLM_MAX_RETRIES (the SDK client is built
  with max_retries=0 so the tenacity layer is the single retry owner —
  no double counting);
- chat()/chat_stream() accept thinking (bool | raw dict) and opts (raw
  extra-body passthrough); legacy callers that pass neither keep the
  exact previous request shape;
- reasoning_content is carried on LLMResponse and never enters content or
  the tool-call/JSON parsing path (ADR-017: in-memory only, never stored).
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    ConflictError,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
)

from .base import LLMMessage, LLMResponse, ModelProvider
from .capability_probe import CapabilityProbe
from .probe_result import ProbeResult
from .prompt_templates import JSON_ACTION_ENVELOPE_BLOCK


def _redact_key(key: str) -> str:
    if len(key) <= 12:
        return "***"
    return key[:8] + "..." + key[-4:]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


# Errors the tenacity layer retries. Mirrors the openai SDK's default
# retryable set (409/429/5xx + connection/timeout; the SDK maps 408 to
# APITimeoutError) so disabling the SDK-internal retries does not
# regress transient-error tolerance.
_RETRYABLE_EXCEPTIONS = (
    RateLimitError,       # 429 — Retry-After aware (gateway rate limits)
    ConflictError,        # 409
    InternalServerError,  # >= 500
    APITimeoutError,      # timeouts incl. 408
    APIConnectionError,
)


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Parse the Retry-After header of a 429 response (seconds form only).

    Returns None when the header is absent or an HTTP-date (unparseable as
    seconds) — callers then fall back to exponential backoff.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") if hasattr(headers, "get") else None
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, seconds)


def _wait_retry_after_or_exponential(retry_state: RetryCallState) -> float:
    """429 → honor Retry-After when present; otherwise capped exponential."""
    outcome = retry_state.outcome
    exception = outcome.exception() if outcome is not None else None
    retry_after = _retry_after_seconds(exception) if exception is not None else None
    if retry_after is not None:
        return retry_after
    return min(60.0, float(2 ** max(0, retry_state.attempt_number - 1)))


def _read_field(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from a dict or an attribute-bearing object (SDK model)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _parse_usage(usage: Any) -> dict[str, Any]:
    """Parse gateway usage into a plain dict.

    prompt/completion/total are always present (0 when usage is missing).
    Optional DeepSeek fields (prompt_cache_hit_tokens /
    prompt_cache_miss_tokens / reasoning tokens) are included only when
    the gateway actually returned them — no fabricated zeros.
    """
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    parsed: dict[str, Any] = {
        "prompt_tokens": _read_field(usage, "prompt_tokens", 0),
        "completion_tokens": _read_field(usage, "completion_tokens", 0),
        "total_tokens": _read_field(usage, "total_tokens", 0),
    }
    for field in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        value = _read_field(usage, field)
        if value is not None:
            parsed[field] = value

    details = _read_field(usage, "completion_tokens_details")
    reasoning = _read_field(details, "reasoning_tokens") if details is not None else None
    if reasoning is None:
        reasoning = _read_field(usage, "reasoning_tokens")
    if reasoning is not None:
        parsed["reasoning_tokens"] = reasoning
    return parsed


class OpenAICompatibleProvider(ModelProvider):
    """OpenAI-compatible provider with capability probing and degradation."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
        probe_on_init: bool = False,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-v4-pro")
        self.timeout = timeout
        self._probe_result: ProbeResult | None = None
        self._client: AsyncOpenAI | None = None
        if max_retries is not None:
            self._max_retries = max(0, max_retries)
        else:
            self._max_retries = _env_int("LLM_MAX_RETRIES", default=2)

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
            # max_retries=0: the tenacity layer in _create_chat_completion is
            # the single retry owner (LLM_MAX_RETRIES semantics + Retry-After
            # handling). Leaving the SDK default on would double-count 429s.
            self._client = AsyncOpenAI(
                base_url=base_url_value,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    @property
    def probe_result(self) -> ProbeResult:
        return self._probe_result  # type: ignore[return-value]

    async def _ensure_probed(self) -> ProbeResult:
        """Lazy probe on first API call. Thread-safe enough for Phase 0."""
        if self._probe_result is None:
            self._probe_result = await self.run_probe()
        return self._probe_result

    async def run_probe(self) -> ProbeResult:
        probe = CapabilityProbe(
            base_url=self.base_url,
            api_key=self.api_key or "",
            model=self.model or "",
        )
        self._probe_result = await probe.run()
        return self._probe_result

    def get_capabilities(self) -> dict[str, Any]:
        return self.probe_result.capabilities

    async def _create_chat_completion(self, kwargs: dict[str, Any]) -> Any:
        """One create() call under the tenacity retry policy.

        Retries transient SDK errors up to LLM_MAX_RETRIES times; a 429
        waits for the gateway's Retry-After header (exponential fallback
        when the header is absent or an HTTP-date).
        """
        retryer = AsyncRetrying(
            retry=retry_if_exception(_is_retryable),
            wait=_wait_retry_after_or_exponential,
            stop=stop_after_attempt(self._max_retries + 1),
            reraise=True,
        )

        # Live-fire fix (gateway fagougou): pass an explicit async _attempt
        # wrapper so every retry attempt awaits a fresh SDK create() call —
        # passing the bound method directly could rebind retry kwargs.
        async def _attempt() -> Any:
            return await self.client.chat.completions.create(**kwargs)

        return await retryer(_attempt)

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        thinking: bool | dict[str, Any] = False,
        opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> LLMResponse:
        probe = await self._ensure_probed()
        caps = probe.capabilities

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
        if caps.get("thinking", False):
            if thinking is True:
                extra_body["thinking"] = {"type": "enabled"}
            elif thinking:
                extra_body["thinking"] = dict(thinking)
        if opts:
            extra_body.update(opts)
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = await self._create_chat_completion(kwargs)
        return self._to_llm_response(response)

    async def chat_stream(  # type: ignore[override, misc]
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        thinking: bool | dict[str, Any] = False,
        opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> AsyncIterator[LLMResponse]:
        probe = await self._ensure_probed()
        caps = probe.capabilities

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
        if caps.get("thinking", False):
            if thinking is True:
                extra_body["thinking"] = {"type": "enabled"}
            elif thinking:
                extra_body["thinking"] = dict(thinking)
        if opts:
            extra_body.update(opts)
        if extra_body:
            kwargs["extra_body"] = extra_body

        stream = await self._create_chat_completion(kwargs)
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
                    model=chunk.model or self.model or "",
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
        reasoning = getattr(msg, "reasoning_content", None)
        if not reasoning:
            # Some gateways place reasoning_content on the choice instead
            # of the message. Either way it stays OUT of content and the
            # tool-call/JSON parsing path (ADR-017: in-memory only).
            reasoning = getattr(choice, "reasoning_content", None)
        return LLMResponse(
            content=msg.content,
            reasoning_content=reasoning,
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
            usage=_parse_usage(response.usage),
            finish_reason=choice.finish_reason or "stop",
            model=response.model,
        )

    def _inject_tool_prompt(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
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
                "\n\n"
                + JSON_ACTION_ENVELOPE_BLOCK
            ),
        }
        return [system_msg] + messages

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
