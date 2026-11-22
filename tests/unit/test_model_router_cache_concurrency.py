"""Parallel sessions must share ONE warm cache entry, not shard it (#2065).

The owner's exact worry: several sessions hitting the same API at once make
the cache look cold and it 'drops'. The defense is structural — a stable
fingerprint key + a sticky prompt_cache_key. This test pins the fingerprint
half offline: concurrent identical questions collapse to ONE model call, and
different questions keep distinct keys so one session cannot poison another.
"""
from __future__ import annotations

import asyncio

from api.model_router_ask import fingerprint
from api.routes import model_router_ask as route_mod


class _MemoryRedis:
    """A fail-open in-memory stand-in for the fingerprint answer cache."""

    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    def get_cached_llm_response(self, key: str) -> dict | None:
        return self.store.get(key)

    def cache_llm_response(self, key: str, value: dict, ttl: int = 3600) -> None:
        self.store[key] = dict(value)


def _ok_answer(question: str) -> dict:
    return {
        "route": "evidence", "route_source": "model", "route_drift": False,
        "rationale": "ok", "content": f"answer to {question}", "verdict": "HELD",
        "detail": "ok", "model": "gpt-6.2-sol", "model_latency_ms": 1,
        "usage": {"cached_tokens_seen": 100, "cache_hit_ratio": 0.95},
        "question_chars": len(question), "locale": "zh",
    }


def test_fingerprint_is_stable_across_sessions_and_questions_are_isolated() -> None:
    # Same question in two "sessions" → same key; whitespace is normalized.
    a = fingerprint("zh", "验收结论怎么来的")
    b = fingerprint("zh", "  验收结论怎么来的  ")
    c = fingerprint("zh", "完全不同的问题")
    assert a == b
    assert a != c
    assert fingerprint("en", "验收结论怎么来的") != a  # locale is part of the key


def test_concurrent_identical_questions_share_one_warm_answer(monkeypatch) -> None:  # noqa: ANN001
    """24 concurrent identical asks reuse the first cached answer."""
    fake = _MemoryRedis()
    calls: list[str] = []

    async def fake_run(question: str, locale: str = "zh") -> dict:
        calls.append(question)
        await asyncio.sleep(0)  # yield — emulate real concurrent in-flight work
        return _ok_answer(question)

    monkeypatch.setattr(route_mod, "_redis", lambda: fake)
    monkeypatch.setattr("api.model_router_ask.run_model_router", fake_run)

    req = route_mod.RouteAskRequest(question="并发测试问题", locale="zh")

    async def strike() -> dict:
        # one candidate reaches the model, the rest read the warm fingerprint
        return await route_mod.route_ask(req)

    async def orchestrate() -> list[dict]:
        # Sequential settle for the first cache fill, then a concurrent burst.
        first = await strike()
        burst = await asyncio.gather(*[strike() for _ in range(23)])
        return [first, *burst]

    results = asyncio.run(orchestrate())
    assert len(calls) == 1, f"model was struck {len(calls)} times — cache fragmented"
    assert results[0]["cached"] is False
    assert all(r["cached"] is True for r in results[1:])
    assert all(r["content"] == "answer to 并发测试问题" for r in results)


def test_concurrent_COLD_misses_coalesce_to_one_model_call(monkeypatch) -> None:  # noqa: ANN001
    """The stampede case: N simultaneous cold asks must NOT strike the model N
    times. One leader loads; the rest ride the same in-flight future."""
    fake = _MemoryRedis()
    calls: list[str] = []

    async def fake_run(question: str, locale: str = "zh") -> dict:
        calls.append(question)
        await asyncio.sleep(0.01)  # widen the race window
        return _ok_answer(question)

    monkeypatch.setattr(route_mod, "_redis", lambda: fake)
    monkeypatch.setattr("api.model_router_ask.run_model_router", fake_run)

    req = route_mod.RouteAskRequest(question="冷启动并发", locale="zh")

    async def go() -> list[dict]:
        return await asyncio.gather(*[route_mod.route_ask(req) for _ in range(20)])

    results = asyncio.run(go())
    assert len(calls) == 1, f"stampede: model struck {len(calls)} times"
    assert all(r["content"] == "answer to 冷启动并发" for r in results)
    assert len(fake.store) == 1  # one fingerprint entry


def test_failed_flight_does_not_poison_later_asks(monkeypatch) -> None:  # noqa: ANN001
    """A failed leader must release its waiters with the SAME honest error and
    leave no half-written flight behind, so a later ask can retry cleanly."""
    from api.errors import ApiError

    fake = _MemoryRedis()
    state = {"fail": True}

    async def flaky(question: str, locale: str = "zh") -> dict:
        if state["fail"]:
            from api.model_router_ask import ModelRouterAskError

            raise ModelRouterAskError("down")
        return _ok_answer(question)

    monkeypatch.setattr(route_mod, "_redis", lambda: fake)
    monkeypatch.setattr("api.model_router_ask.run_model_router", flaky)

    req = route_mod.RouteAskRequest(question="会失败", locale="zh")

    async def go() -> None:
        import pytest

        with pytest.raises(ApiError):
            await asyncio.gather(*[route_mod.route_ask(req) for _ in range(5)])
        state["fail"] = False
        ok = await route_mod.route_ask(req)
        assert ok["content"] == "answer to 会失败"

    asyncio.run(go())
    assert len(fake.store) == 1  # only the successful retry cached


def test_different_questions_keep_distinct_cache_entries(monkeypatch) -> None:  # noqa: ANN001
    fake = _MemoryRedis()
    monkeypatch.setattr(route_mod, "_redis", lambda: fake)
    monkeypatch.setattr(
        "api.model_router_ask.run_model_router",
        lambda q, locale="zh": asyncio.sleep(0, result=_ok_answer(q)),
    )

    async def go() -> None:
        await route_mod.route_ask(route_mod.RouteAskRequest(question="问题甲", locale="zh"))
        await route_mod.route_ask(route_mod.RouteAskRequest(question="问题乙", locale="zh"))

    asyncio.run(go())
    assert len(fake.store) == 2  # no cross-question cache collision
