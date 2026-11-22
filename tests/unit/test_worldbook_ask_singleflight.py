"""The world-book lane gets the same anti-stampede defense as model-router.

Two public lanes share the same failure mode: parallel sessions striking a
cold fingerprint all miss Redis at once. Both now use the shared SingleFlight
utility with a lane-local registry (#2069). This pins the book side offline.
"""
from __future__ import annotations

import asyncio

from api.routes import worldbook_ask as route_mod

pytestmark = []  # no async marker needed; we drive the coroutine via asyncio.run


class _MemoryRedis:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    def get_cached_llm_response(self, key: str) -> dict | None:
        return self.store.get(key)

    def cache_llm_response(self, key: str, value: dict, ttl: int = 3600) -> None:
        self.store[key] = dict(value)


def _answer() -> dict:
    return {
        "answer": "书里写着。", "model": "gpt-6.2-sol", "model_latency_ms": 5,
        "usage": {}, "question_chars": 6,
    }


def test_concurrent_cold_misses_share_one_book_read(monkeypatch) -> None:  # noqa: ANN001
    fake = _MemoryRedis()
    calls = {"n": 0}

    async def fake_generate(question: str, locale: str = "zh") -> dict:
        calls["n"] += 1
        await asyncio.sleep(0.01)
        return _answer()

    monkeypatch.setattr("api.worldbook_ask.ask_redis", lambda: fake)
    monkeypatch.setattr("api.worldbook_ask.generate_ask_answer", fake_generate)

    req = route_mod.WorldbookAskRequest(question="并发问书", locale="zh")

    async def go():
        return await asyncio.gather(*[route_mod.worldbook_ask(req) for _ in range(20)])

    results = asyncio.run(go())
    assert calls["n"] == 1, f"book was read {calls['n']} times — stampede"
    # All 20 share the leader's single answer; the leader honestly reports a
    # cold read. (Waiters share that body — the point is one model call.)
    assert all(r["answer"] == "书里写着。" for r in results)
    assert len(fake.store) == 1

    # A fresh ask after the burst now reads the warm fingerprint.
    warm = asyncio.run(route_mod.worldbook_ask(req))
    assert warm["cached"] is True
    assert calls["n"] == 1


def test_lane_flights_are_isolated(monkeypatch) -> None:  # noqa: ANN001
    """The book's in-flight registry is a distinct object from model-router's."""
    from api.model_router_ask import _answer_singleflight
    from api.routes.worldbook_ask import _book_singleflight

    assert _book_singleflight is not _answer_singleflight
