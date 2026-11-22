"""End-to-end HTTP checks for POST /route/ask against the REAL FastAPI app.

Unit tests cover the lane logic; this pins the assembly — route registration,
request validation, the honest error mapping, and the fingerprint cache —
through the actual ASGI app that a browser talks to. No token is spent: the
provider is injected as a fake.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.auth import enforce_rate_limit
from api.server import app
from api.routes import model_router_ask as route_mod

pytestmark = pytest.mark.integration


class _MemoryRedis:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    def get_cached_llm_response(self, key: str) -> dict | None:
        return self.store.get(key)

    def cache_llm_response(self, key: str, value: dict, ttl: int = 3600) -> None:
        self.store[key] = dict(value)


def _answer(route: str = "worldbook", locale: str = "zh") -> dict:
    return {
        "route": route, "route_source": "model", "route_drift": False,
        "rationale": "ok", "content": "卷零写着创世。", "verdict": "HELD",
        "detail": "ok", "model": "gpt-6.2-sol", "model_latency_ms": 5,
        "usage": {"cached_tokens_seen": 100, "cache_hit_ratio": 0.9},
        "question_chars": 8, "locale": locale,
    }


@pytest.fixture()
def http():
    app.dependency_overrides[enforce_rate_limit] = lambda: None
    fake = _MemoryRedis()
    original = route_mod._redis
    route_mod._redis = lambda: fake
    calls = {"n": 0, "boom": False}

    async def fake_run(question: str, locale: str = "zh") -> dict:
        calls["n"] += 1
        if calls["boom"]:
            import api.model_router_ask as lane

            raise lane.ModelRouterAskError("down")
        return _answer(locale=locale)

    import api.model_router_ask as lane

    original_run = lane.run_model_router
    lane.run_model_router = fake_run
    try:
        yield TestClient(app), fake, calls
    finally:
        app.dependency_overrides.pop(enforce_rate_limit, None)
        route_mod._redis = original
        lane.run_model_router = original_run


def test_route_ask_happy_path_then_cached(http) -> None:  # noqa: ANN001
    client, fake, calls = http
    first = client.post("/route/ask", json={"question": "世界书从哪开始", "locale": "zh"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["route"] == "worldbook"
    assert body["verdict"] == "HELD"
    assert body["cached"] is False
    assert "latency_ms" in body

    second = client.post("/route/ask", json={"question": "世界书从哪开始", "locale": "zh"})
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert calls["n"] == 1  # model struck once; the second read the fingerprint
    assert len(fake.store) == 1


def test_route_ask_rejects_extra_and_empty(http) -> None:  # noqa: ANN001
    client, _, _ = http
    assert client.post("/route/ask", json={"question": "hi", "extra": 1}).status_code == 422
    assert client.post("/route/ask", json={"question": ""}).status_code == 422


def test_route_ask_locale_normalized(http) -> None:  # noqa: ANN001
    client, fake, _ = http
    resp = client.post("/route/ask", json={"question": "where", "locale": "EN"})
    assert resp.status_code == 200
    assert resp.json()["locale"] == "en"
    assert len(fake.store) == 1


def test_route_ask_model_down_is_honest_503(http) -> None:  # noqa: ANN001
    client, _, calls = http
    calls["boom"] = True
    resp = client.post("/route/ask", json={"question": "会失败", "locale": "zh"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
