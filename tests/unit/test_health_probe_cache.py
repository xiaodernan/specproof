"""The readiness probe may never be a per-request deep check.

Measured 2026-11-18 (this host, uvicorn single worker + MYSQL_POOL_SIZE=8):
/health open a fresh MySQL probe per inbound request collapsed at ~25 rps
(94% of calls timed out at 5 s under k6 constant-arrival-rate=100, 30 s).
The fix samples the deep probe for SPECPROOF_HEALTH_PROBE_TTL_SECONDS.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from api.server import app


def _reset(monkeypatch: pytest.MonkeyPatch, ttl: str | None = None) -> None:
    from api import server as srv

    srv._HEALTH_CACHE.update(at=0.0, payload=None)
    if ttl is not None:
        monkeypatch.setenv("SPECPROOF_HEALTH_PROBE_TTL_SECONDS", ttl)
    else:
        monkeypatch.delenv("SPECPROOF_HEALTH_PROBE_TTL_SECONDS", raising=False)


def _count_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"n": 0}

    class FakeStore:
        def is_ready(self) -> bool:
            calls["n"] += 1
            time.sleep(0.02)
            return True

    import storage.mysql as ms
    import storage.redis as rs

    monkeypatch.setattr(ms, "MySQLStore", FakeStore)
    monkeypatch.setattr(rs, "RedisStore", FakeStore)
    return calls


def test_health_is_sampled_not_per_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _count_calls(monkeypatch)
    _reset(monkeypatch, ttl="2.0")
    c = TestClient(app)
    for _ in range(6):
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
    assert calls["n"] == 2  # one deep probe (mysql+redis), the rest were cache hits


def test_health_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _count_calls(monkeypatch)
    _reset(monkeypatch, ttl="0.15")
    c = TestClient(app)
    c.get("/health")
    c.get("/health")
    assert calls["n"] == 2
    time.sleep(0.16)
    c.get("/health")
    assert calls["n"] == 4


def test_health_ttl_zero_disables_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _count_calls(monkeypatch)
    _reset(monkeypatch, ttl="0")
    c = TestClient(app)
    for _ in range(3):
        c.get("/health")
    assert calls["n"] == 6  # every probe ran deep, per-request as before


def test_health_probe_is_single_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _count_calls(monkeypatch)
    _reset(monkeypatch, ttl="2.0")
    c = TestClient(app)
    barrier = threading.Barrier(2)
    results: list[int] = []

    def strike() -> None:
        barrier.wait()
        results.append(c.get("/health").status_code)

    t1 = threading.Thread(target=strike)
    t2 = threading.Thread(target=strike)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert results == [200, 200]
    assert calls["n"] == 2  # one deep probe; the second thread hit the cache inside the lock


def test_health_degraded_path_still_sampled(monkeypatch: pytest.MonkeyPatch) -> None:
    class DownStore:
        def is_ready(self) -> bool:
            return False

    import storage.mysql as ms
    import storage.redis as rs

    monkeypatch.setattr(ms, "MySQLStore", DownStore)
    monkeypatch.setattr(rs, "RedisStore", DownStore)
    _reset(monkeypatch, ttl="2.0")
    c = TestClient(app)
    first = c.get("/health").json()
    second = c.get("/health").json()
    assert first["status"] == "degraded"
    assert first["mysql"] is False and first["redis"] is False
    assert second["status"] == "degraded"
