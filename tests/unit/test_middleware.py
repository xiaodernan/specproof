"""Request-ID + payload-limit middleware tests (TestClient, real app).

Covers: request-id generation / pass-through / per-request uniqueness /
response header echo / structured log field / contextvar reset; payload
limit 413 (before auth) / normal pass-through / non-JSON untouched /
non-API paths untouched / SSE streaming unaffected.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.jobs as jobs_module
from api.middleware import DEFAULT_MAX_JSON_BYTES
from api.server import app

API_KEY = "mw-test-key"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)
    monkeypatch.delenv("SPECPROOF_MAX_JSON_BYTES", raising=False)


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


class _FakeRedisRateLimit:
    @property
    def client(self) -> _FakeRedisRateLimit:
        return self

    def incr(self, key: str) -> int:
        return 1

    def expire(self, key: str, ttl: int) -> None:
        return None


class _FakeRedisStream:
    def __init__(self) -> None:
        self.served = False

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 50
    ) -> list[dict[str, Any]]:
        del job_id, from_id, count
        if self.served:
            return []
        self.served = True
        return [{
            "id": "1-0",
            "node": "compile",
            "status": "done",
            "percent": 100,
            "message": "ok",
            "at": "2026-01-01T00:00:00Z",
        }]


class _FakeMySQLStore:
    def __init__(self) -> None:
        pass

    def create_job_with_outbox(self, job: dict[str, Any]) -> str:
        return job["id"]


@pytest.fixture()
def fake_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs_module, "MySQLStore", _FakeMySQLStore)
    monkeypatch.setattr("storage.redis.RedisStore", _FakeRedisRateLimit)
    monkeypatch.setattr(jobs_module, "_redis", _FakeRedisStream())


# ── Request-ID ──────────────────────────────────────────────────────────────


def test_request_id_generated_when_absent() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    request_id = resp.headers.get("X-Request-ID", "")
    assert len(request_id) == 16
    assert all(c in "0123456789abcdef" for c in request_id)


def test_request_id_passthrough() -> None:
    client = TestClient(app)
    resp = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.headers["X-Request-ID"] == "trace-abc-123"


def test_request_id_unique_per_request() -> None:
    client = TestClient(app)
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert first and second
    assert first != second


def test_request_id_on_protected_api() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/health", headers=_headers())
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")


def test_request_id_still_echoed_on_413(monkeypatch: pytest.MonkeyPatch) -> None:
    # RequestID runs outermost, so even the payload-limit rejection carries it.
    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "64")
    client = TestClient(app)
    resp = client.post("/jobs", json={"x": "y" * 1000})
    assert resp.status_code == 413
    assert resp.headers.get("X-Request-ID")


def test_request_id_logged_as_structured_field(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="api.middleware")
    client = TestClient(app)
    resp = client.get("/health")
    records = [
        r
        for r in caplog.records
        if r.name == "api.middleware"
        and getattr(r, "request_id", None) == resp.headers["X-Request-ID"]
    ]
    assert records, "middleware must log the request with the request_id field"


def test_request_id_contextvar_reset_after_request() -> None:
    from observability.logging import request_id_var

    client = TestClient(app)
    client.get("/health")
    assert request_id_var.get() == ""


# ── Payload limit ───────────────────────────────────────────────────────────


def test_payload_limit_default_is_10_mib() -> None:
    assert DEFAULT_MAX_JSON_BYTES == 10 * 1024 * 1024


def test_payload_over_limit_rejected_before_auth(
    monkeypatch: pytest.MonkeyPatch, fake_stores: None
) -> None:
    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "1024")
    client = TestClient(app)
    big_body = {"repo_path": "x" * 2048}
    # No API key on purpose: 413 must win over 401 (middleware before auth).
    resp = client.post("/jobs", json=big_body)
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert "1024 bytes" in detail


def test_payload_under_limit_passes(monkeypatch: pytest.MonkeyPatch, fake_stores: None) -> None:
    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "1024")
    client = TestClient(app)
    resp = client.post(
        "/jobs",
        json={
            "repo_path": "C:\\repo",
            "base_ref": "base",
            "head_ref": "head",
            "spec_path": "C:\\spec.txt",
            "depth": "FAST",
        },
        headers=_headers(),
    )
    assert resp.status_code == 202


def test_non_json_content_type_not_limited(
    monkeypatch: pytest.MonkeyPatch, fake_stores: None
) -> None:
    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "64")
    client = TestClient(app)
    resp = client.post(
        "/jobs",
        content=b"x" * 4096,
        headers={"content-type": "text/plain", **_headers()},
    )
    assert resp.status_code != 413


def test_non_api_path_not_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "64")
    client = TestClient(app)
    resp = client.post("/misc", json={"pad": "x" * 4096}, headers=_headers())
    assert resp.status_code != 413


def test_get_requests_never_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "64")
    client = TestClient(app)
    resp = client.get("/api/v1/health", headers=_headers())
    assert resp.status_code == 200


# ── SSE unaffected ──────────────────────────────────────────────────────────


def test_sse_progress_stream_unaffected(
    fake_stores: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The real endpoint loops forever by design (SSE); the middlewares must
    # not buffer or break the stream. Simulate a client disconnect after the
    # first event so the generator terminates cleanly and the stream ends.
    from fastapi import Request

    checks: list[bool] = []

    async def fake_is_disconnected(self: Request) -> bool:
        del self
        checks.append(True)
        return len(checks) > 1  # connected for the first check, then gone

    async def fast_sleep(delay: float) -> None:
        # No-op sleep: the disconnect simulation above guarantees the
        # generator terminates after one event, so nothing spins here.
        del delay
        return None

    monkeypatch.setattr(jobs_module.Request, "is_disconnected", fake_is_disconnected)
    monkeypatch.setattr(jobs_module.asyncio, "sleep", fast_sleep)
    client = TestClient(app)
    with client.stream("GET", "/jobs/j-1/progress", headers=_headers()) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers.get("X-Request-ID")
        lines = list(resp.iter_lines())
    assert any(line.startswith("id: 1-0") for line in lines)
    assert any(line.startswith("event: progress") for line in lines)
    assert any(line.startswith("data: ") for line in lines)


def test_sse_requires_key_still_401(fake_stores: None) -> None:
    client = TestClient(app)
    resp = client.get("/jobs/j-1/progress")
    assert resp.status_code == 401
