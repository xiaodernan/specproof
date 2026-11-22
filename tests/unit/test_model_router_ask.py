"""The product face of the model-router StateGraph — offline, zero token.

The fake provider answers the two calls in sequence; nothing touches the
network. These tests pin the exact semantics the graph advertises: the model's
route label drives which lane writes content, a hallucinated route produces no
content call, a verdict is refused, and both calls share one sticky cache key.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from api.model_router_ask import (
    MAX_QUESTION_CHARS,
    ModelRouterAskError,
    _merge_usage,
    fingerprint,
    run_model_router,
)
from providers.base import LLMResponse


class _ScriptedProvider:
    """Returns scripted responses in order; records every chat call's opts."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, messages, *, response_format=None, opts=None, **_):  # noqa: ANN001, ANN003
        self.calls.append({
            "messages": messages,
            "response_format": response_format,
            "opts": opts or {},
        })
        return self.responses.pop(0)

    async def close(self) -> None:
        pass


def _route(label: str, usage: dict | None = None) -> LLMResponse:
    return LLMResponse(
        content=json.dumps({"route": label, "rationale": "because"}, ensure_ascii=False),
        usage=usage or {},
        model="gpt-6.2-sol",
    )


def test_question_is_sanitized_and_bounded() -> None:
    from api.model_router_ask import _sanitize

    assert _sanitize("  你好\r\n 世界 ") == "你好 世界"
    assert len(_sanitize("a" * 2000)) == MAX_QUESTION_CHARS


def test_fingerprint_stable_and_sensitive() -> None:
    assert fingerprint("zh", "你好") == fingerprint("zh", "你好")
    assert fingerprint("zh", "你好") != fingerprint("en", "你好")
    assert fingerprint("zh", "你好") != fingerprint("zh", "你好呀")


def test_model_route_drives_content_and_both_calls_share_sticky_key() -> None:
    provider = _ScriptedProvider([
        _route("evidence", {"prompt_tokens": 100, "prompt_cache_hit_tokens": 80}),
        LLMResponse(content="看 diff 与证据链。", usage={"prompt_tokens": 100, "prompt_cache_hit_tokens": 80}, model="gpt-6.2-sol"),
    ])
    out = asyncio.run(run_model_router(
        "权限校验的回归怎么定位", "zh",
        provider_factory=lambda **_: provider,
    ))
    assert out["route"] == "evidence"
    assert out["route_source"] == "model"
    assert out["verdict"] == "HELD"
    assert "证据" in out["content"] or out["content"]
    assert len(provider.calls) == 2
    # The model route call asks for JSON; the content call does not.
    assert provider.calls[0]["response_format"] == {"type": "json_object"}
    assert provider.calls[1]["response_format"] is None
    # THE cache guarantee: one sticky key on both calls, no per-request nonce.
    keys = {c["opts"].get("prompt_cache_key") for c in provider.calls}
    assert keys == {"specproof-model-router"}


def test_route_drift_makes_no_content_call() -> None:
    provider = _ScriptedProvider([
        _route("hallucinated-lane"),
    ])
    out = asyncio.run(run_model_router(
        "随便问问", "zh", provider_factory=lambda **_: provider,
    ))
    assert out["route"] == ""
    assert out["verdict"] == "ROUTE-DRIFT"
    assert out["content"] == ""
    assert len(provider.calls) == 1  # no second, content call


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_verdict_words_are_refused(lang: str) -> None:
    bad = "验收通过，批准发布" if lang == "zh" else "this is approved and blocked"
    provider = _ScriptedProvider([
        _route("evidence"),
        LLMResponse(content=bad, usage={}, model="gpt-6.2-sol"),
    ])
    out = asyncio.run(run_model_router(
        "能发布吗", lang, provider_factory=lambda **_: provider,
    ))
    assert out["verdict"] == "VERDICT-LEAK"
    assert out["content"] == ""


def test_cache_token_reading_survives_both_gateway_shapes() -> None:
    # aizzz / normalized shape and raw OpenAI shape both count.
    merged = _merge_usage(
        {"prompt_tokens": 100, "prompt_cache_hit_tokens": 80},
        {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 75}},
    )
    assert merged["cached_tokens_seen"] == 155
    assert merged["cache_hit_ratio"] == round(155 / 200, 4)


def test_provider_failure_is_one_honest_error() -> None:
    class Boom:
        def __init__(self, **_: object) -> None:
            pass

        async def chat(self, *a, **k):  # noqa: ANN001, ANN003
            raise RuntimeError("gateway down")

        async def close(self) -> None:
            pass

    with pytest.raises(ModelRouterAskError):
        asyncio.run(run_model_router("你好", "zh", provider_factory=Boom))


def test_empty_question_rejected() -> None:
    with pytest.raises(ValueError):
        asyncio.run(run_model_router("   ", "zh", provider_factory=lambda **_: _ScriptedProvider([])))
