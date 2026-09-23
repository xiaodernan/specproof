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
  the tool-call/JSON parsing path (ADR-017: in-memory only, never stored);
- ClientPolicy gate (W44/W60 wiring): when SPECPROOF_PROVIDER_POLICY=1, a
  chat() call tagged with kind= flows through providers/client_policy.py
  (two-tier router + classify_retry retry matrix + semantic cache for
  draft/diagnose); when the gate is unset, the exact legacy path runs —
  the policy layer is never even constructed.
"""
from __future__ import annotations

import asyncio
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
from .client_policy import ClientPolicy, client_policy_enabled
from .probe_result import ProbeResult
from .prompt_templates import JSON_ACTION_ENVELOPE_BLOCK
from .responses_protocol import field as response_field
from .responses_protocol import normalize_base_url, parse_response, request_kwargs, tool_call


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
        policy: ClientPolicy | None = None,
        protocol: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        from .config import load_model_config

        config = load_model_config() if not (base_url and api_key and model) else {}
        self.base_url = str(base_url or config.get("base_url") or "").rstrip("/")
        self.api_key = str(api_key or config.get("api_key") or "")
        self.model = str(model or config.get("model") or "deepseek-v4-pro")
        # Explicit model selection must not inherit another model's stored protocol.
        model_from_config = model is None and not os.getenv("LLM_MODEL")
        self.protocol = protocol or os.getenv("LLM_PROTOCOL") or (
            str(config.get("protocol") or "") if model_from_config else ""
        ) or ("responses" if self.model.startswith("gpt-6") else "chat")
        if self.protocol not in ("responses", "chat", "chat_completions"):
            raise ValueError("LLM protocol must be responses or chat")
        self.reasoning_effort = (
            reasoning_effort if reasoning_effort is not None
            else os.environ["LLM_REASONING_EFFORT"] if "LLM_REASONING_EFFORT" in os.environ
            else str(config.get("reasoning_effort", "")) if model_from_config
            else "max" if self.model.startswith("gpt-6") else None
        )
        self.timeout = timeout
        self._probe_result: ProbeResult | None = None
        self._client: AsyncOpenAI | None = None
        if max_retries is not None:
            self._max_retries = max(0, max_retries)
        else:
            self._max_retries = _env_int("LLM_MAX_RETRIES", default=2)

        # W44/W60 wiring — the ClientPolicy gate. Default off: when the env
        # switch is unset the provider never constructs a policy and every
        # call runs the exact legacy path (byte-identical behavior).
        self._policy: ClientPolicy | None
        if policy is not None:
            # Explicit programmatic opt-in (tests / embedders); the env gate
            # below is the production switch.
            self._policy = policy
        elif client_policy_enabled():
            # max_attempts mirrors the tenacity budget: LLM_MAX_RETRIES
            # retries means max_retries + 1 attempts on the policy path too.
            self._policy = ClientPolicy(max_attempts=max(1, self._max_retries + 1))
        else:
            self._policy = None
        # One SDK client per routed tier base_url (policy calls only; the
        # legacy strong client remains self._client). Empty when policy off.
        self._policy_clients: dict[str, AsyncOpenAI] = {}

        if not self.api_key or self.api_key == "replace_me":
            raise ValueError(
                "LLM_API_KEY is not set or is placeholder 'replace_me'. "
                "Set the environment variable or pass api_key explicitly."
            )

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = self._make_client(self.base_url)
        return self._client

    def _make_client(self, base_url: str) -> AsyncOpenAI:
        """Build one AsyncOpenAI client for a base_url (adds the /v1 suffix)."""
        base_url_value = normalize_base_url(base_url)
        # max_retries=0: the tenacity layer in _create_chat_completion is
        # the single retry owner (LLM_MAX_RETRIES semantics + Retry-After
        # handling). Leaving the SDK default on would double-count 429s.
        return AsyncOpenAI(
            base_url=base_url_value,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,
        )

    @property
    def probe_result(self) -> ProbeResult:
        return self._probe_result  # type: ignore[return-value]

    async def _ensure_probed(self) -> ProbeResult:
        """Lazy probe on first API call. Thread-safe enough for Phase 0."""
        if self._probe_result is None:
            self._probe_result = await self.run_probe()
        return self._probe_result

    async def run_probe(self) -> ProbeResult:
        if self.protocol == "responses":
            # One real streamed response measures reachability + streaming.
            # Unsupported/unexercised features stay absent, not fabricated.
            try:
                async with asyncio.timeout(min(self.timeout, 30.0)):
                    async for _ in self.chat_stream(
                        [LLMMessage(role="user", content="Reply with just: OK")],
                        timeout=min(self.timeout, 30.0),
                    ):
                        pass
            except Exception as exc:
                self._probe_result = ProbeResult(
                    provider="openai_compatible", base_url=self.base_url, model=self.model,
                    capabilities={"chat": False, "streaming": False},
                    errors=[f"Responses protocol check failed: {type(exc).__name__}"],
                )
            assert self._probe_result is not None
            return self._probe_result
        probe = CapabilityProbe(
            base_url=self.base_url,
            api_key=self.api_key or "",
            model=self.model or "",
        )
        self._probe_result = await probe.run()
        return self._probe_result

    def get_capabilities(self) -> dict[str, Any]:
        if self._probe_result is None:
            raise RuntimeError("Provider capabilities have not been measured")
        return self.probe_result.capabilities

    def _record_responses_capabilities(
        self, result: LLMResponse, *, streaming: bool = False,
        response_format: dict[str, Any] | None = None, tool_choice: str | None = None,
    ) -> None:
        caps = dict(self._probe_result.capabilities) if self._probe_result else {}
        caps["chat"] = True
        if streaming:
            caps["streaming"] = True
        if result.tool_calls:
            caps["tool_calls"] = True
            if tool_choice == "required":
                caps["strict_tool_calls"] = True
        if response_format and result.content:
            try:
                json.loads(result.content)
            except (ValueError, TypeError):
                caps["json_output"] = False
            else:
                caps["json_output"] = True
        if result.usage:
            caps["usage_reporting"] = True
        if result.usage.get("reasoning_tokens", 0) > 0:
            caps["thinking"] = True
            if result.tool_calls:
                caps["thinking_with_tools"] = True
        self._probe_result = ProbeResult(
            provider="openai_compatible", base_url=self.base_url,
            model=self.model, capabilities=caps,
        )

    async def _create_response(self, kwargs: dict[str, Any]) -> Any:
        retryer = AsyncRetrying(
            retry=retry_if_exception(_is_retryable), wait=_wait_retry_after_or_exponential,
            stop=stop_after_attempt(self._max_retries + 1), reraise=True,
        )

        async def attempt() -> Any:
            return await self.client.responses.create(**kwargs)

        return await retryer(attempt)

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

    @staticmethod
    async def _raw_create(client: AsyncOpenAI, kwargs: dict[str, Any]) -> Any:
        """One raw SDK completion call on an injected client (policy path)."""
        return await client.chat.completions.create(**kwargs)

    def _client_for_base_url(self, base_url: str) -> AsyncOpenAI:
        """Resolve a routed base_url to an SDK client (policy path).

        An empty base_url — or one that resolves to this provider's own
        endpoint — reuses the legacy client, so a strong route with no
        explicit config is identical to today. Any other base_url gets a
        dedicated cached client built with the same construction parameters
        (max_retries=0 — the policy retry layer is the single retry owner).
        """
        if not base_url or base_url.rstrip("/") == self.base_url:
            return self.client
        client = self._policy_clients.get(base_url)
        if client is None:
            client = self._make_client(base_url)
            self._policy_clients[base_url] = client
        return client

    async def _policy_chat(
        self, policy: ClientPolicy, kind: str, kwargs: dict[str, Any]
    ) -> Any:
        """One policy-governed call: ClientPolicy routes, caches and retries.

        The policy decides WHICH client each attempt rides (cheap vs strong
        tier) and whether the semantic cache can short-circuit; this method
        supplies the client factory and the raw SDK call so the policy never
        touches SDK construction, response parsing or client lifecycle.
        """
        return await policy.execute(
            kind,
            kwargs,
            create=self._raw_create,
            make_client=self._client_for_base_url,
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        thinking: bool | dict[str, Any] = False,
        opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
        kind: str | None = None,
    ) -> LLMResponse:
        if self.protocol == "responses":
            kwargs: dict[str, Any] = request_kwargs(
                self.model, messages, effort=self.reasoning_effort, tools=tools,
                tool_choice=tool_choice, response_format=response_format, opts=opts,
                timeout=timeout,
            )
            result = parse_response(await self._create_response(kwargs))
            self._record_responses_capabilities(
                result, response_format=response_format, tool_choice=tool_choice,
            )
            return result
        probe = await self._ensure_probed()
        caps = probe.capabilities

        oai_messages = self._to_openai_messages(messages)
        kwargs = {
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

        policy = self._policy
        if policy is not None and kind is not None:
            # W44/W60: policy-governed call (route + classify_retry matrix +
            # semantic cache). Only kind-tagged calls under an enabled policy
            # leave the legacy path; everything else stays byte-identical.
            response = await self._policy_chat(policy, kind, kwargs)
        else:
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
        if self.protocol == "responses":
            async for result in self._responses_stream(messages, tools, opts, timeout):
                yield result
            return
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

    async def _responses_stream(
        self, messages: list[LLMMessage], tools: list[dict[str, Any]] | None,
        opts: dict[str, Any] | None, timeout: float,
    ) -> AsyncIterator[LLMResponse]:
        kwargs = request_kwargs(
            self.model, messages, effort=self.reasoning_effort, tools=tools,
            opts=opts, timeout=timeout,
        )
        stream = await self._create_response({**kwargs, "stream": True})
        completed = False
        saw_text_delta = False
        saw_tool_item = False
        emitted_calls: set[str] = set()
        try:
            async for event in stream:
                kind = response_field(event, "type", "")
                if kind == "response.output_text.delta":
                    saw_text_delta = True
                    yield LLMResponse(
                        content=response_field(event, "delta", ""),
                        model=self.model, finish_reason="",
                    )
                elif kind == "response.output_item.done":
                    item = response_field(event, "item")
                    if response_field(item, "type") == "function_call":
                        saw_tool_item = True
                        call = tool_call(item)
                        emitted_calls.add(str(call["id"]))
                        yield LLMResponse(tool_calls=[call], model=self.model, finish_reason="")
                elif kind == "response.completed":
                    result = parse_response(response_field(event, "response"))
                    self._record_responses_capabilities(
                        result, streaming=saw_text_delta or saw_tool_item,
                    )
                    completed = True
                    # Completion contains the whole answer. Do not replay text
                    # or calls already emitted in earlier stream events.
                    yield LLMResponse(
                        content=None if saw_text_delta else result.content,
                        tool_calls=[
                            call for call in result.tool_calls
                            if str(call["id"]) not in emitted_calls
                        ],
                        usage=result.usage, finish_reason=result.finish_reason, model=result.model,
                    )
                elif kind in ("response.failed", "response.incomplete", "error"):
                    raise RuntimeError(f"Model stream did not complete ({kind})")
                elif kind == "response.refusal.delta":
                    raise RuntimeError("The model declined this request; no result was produced")
            if not completed:
                raise RuntimeError("Model stream ended before a completed response")
        finally:
            await stream.close()

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
        for client in self._policy_clients.values():
            await client.close()
        self._policy_clients.clear()
        if self._client:
            await self._client.close()
            self._client = None
