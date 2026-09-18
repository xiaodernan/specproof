"""Translate the project's chat interface into stateless Responses requests."""
from __future__ import annotations

from typing import Any

from .base import LLMMessage, LLMResponse


def field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def normalize_base_url(value: str) -> str:
    value = value.rstrip("/")
    return value if value.endswith("/v1") else value + "/v1"


def request_kwargs(
    model: str, messages: list[LLMMessage], *, effort: str | None,
    tools: list[dict[str, Any]] | None = None, tool_choice: str | None = None,
    response_format: dict[str, Any] | None = None, opts: dict[str, Any] | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            if not message.tool_call_id:
                raise ValueError("Tool output must reference its tool_call_id")
            items.append({
                "type": "function_call_output", "call_id": message.tool_call_id,
                "output": message.content or "",
            })
            continue
        if message.content is not None:
            items.append({"role": message.role, "content": message.content})
        for call in message.tool_calls or []:
            function = call.get("function", {})
            items.append({
                "type": "function_call", "call_id": call["id"],
                "name": function["name"], "arguments": function["arguments"],
            })
    kwargs: dict[str, Any] = {
        "model": model, "input": items, "store": False, "timeout": timeout,
    }
    if effort:
        kwargs["reasoning"] = {"effort": effort}
    if tools:
        kwargs["tools"] = [
            {"type": "function", **tool["function"]} if "function" in tool else dict(tool)
            for tool in tools
        ]
        # Chat tools default to non-strict. Preserve that contract: existing
        # schemas contain optional properties and are not strict-JSON schemas.
        for tool in kwargs["tools"]:
            if tool.get("type") == "function":
                tool.setdefault("strict", False)
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    if response_format:
        fmt = dict(response_format)
        if fmt.get("type") == "json_schema":
            fmt = {"type": "json_schema", **fmt.get("json_schema", {})}
        kwargs["text"] = {"format": fmt}
    if opts:
        extra = dict(opts)
        if "max_tokens" in extra:
            extra.setdefault("max_output_tokens", extra.pop("max_tokens"))
        effort_override = extra.pop("reasoning_effort", None)
        if effort_override:
            extra["reasoning"] = {"effort": effort_override}
        # These chat-only sampling/thinking controls are not accepted by Astra.
        for name in ("temperature", "top_p", "thinking"):
            extra.pop(name, None)
        if extra:
            kwargs["extra_body"] = extra
    return kwargs


def usage_data(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    result = {
        "prompt_tokens": field(usage, "input_tokens", 0),
        "completion_tokens": field(usage, "output_tokens", 0),
        "total_tokens": field(usage, "total_tokens", 0),
    }
    cached = field(field(usage, "input_tokens_details"), "cached_tokens")
    reasoning = field(field(usage, "output_tokens_details"), "reasoning_tokens")
    if cached is not None:
        result["prompt_cache_hit_tokens"] = cached
        result["prompt_cache_miss_tokens"] = max(0, result["prompt_tokens"] - cached)
    if reasoning is not None:
        result["reasoning_tokens"] = reasoning
    return result


def tool_call(item: Any) -> dict[str, Any]:
    return {
        "id": field(item, "call_id"), "type": "function",
        "function": {"name": field(item, "name"), "arguments": field(item, "arguments", "")},
    }


def parse_response(response: Any) -> LLMResponse:
    status = field(response, "status")
    if status != "completed":
        # Do not echo gateway error bodies (they can contain request credentials).
        reason = field(field(response, "incomplete_details"), "reason", "unknown")
        raise RuntimeError(f"Model response did not complete (status={status}, reason={reason})")
    texts: list[str] = []
    calls: list[dict[str, Any]] = []
    for item in field(response, "output", []) or []:
        if field(item, "type") == "function_call":
            calls.append(tool_call(item))
        elif field(item, "type") == "message":
            for content in field(item, "content", []) or []:
                if field(content, "type") == "refusal":
                    raise RuntimeError("The model declined this request; no result was produced")
                if field(content, "type") == "output_text":
                    texts.append(field(content, "text", ""))
    if not texts and not calls:
        raise RuntimeError("The model returned no text or tool calls")
    return LLMResponse(
        content="".join(texts) or None, tool_calls=calls,
        usage=usage_data(field(response, "usage")), model=field(response, "model", ""),
        finish_reason="tool_calls" if calls else "stop",
    )
