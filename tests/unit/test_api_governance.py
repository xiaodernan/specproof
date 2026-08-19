"""Unit tests for the §14.3 API governance hardening.

Covers the three cross-cutting contracts of this lane:

1. The verify-job progress SSE stream carries a monotonic sequence number
   plus event type / stage / status / percentage / summary / timestamp,
   resumes after Last-Event-ID, and replays the terminal event with an
   identical payload (idempotent repeat consumption).
2. error_response derives 'retryable' from the error-code failure class:
   client/permission/not-found/conflict are permanent, while
   degrade/execution-failure/rate-limit/internal may succeed on retry;
   unknown codes fail closed to False.
3. POST /jobs enforces the documented field allowlist: arbitrary
   env/command/docker/output-path parameters are refused with
   422 VALIDATION_FAILED naming the offending field.

No live infra: the SSE generator is driven directly against a fake reader
(exactly like test_agent_console_api.py's disconnect tests) and the HTTP
whitelist tests use TestClient with faked MySQL/Redis stores.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.jobs as jobs_module
from api.errors import (
    AUTH_REQUIRED,
    EVIDENCE_UNVERIFIED,
    INTERNAL,
    JOB_NOT_FOUND,
    PAYLOAD_TOO_LARGE,
    PROVIDER_UNAVAILABLE,
    QUOTA_EXCEEDED,
    RATE_LIMITED,
    STATE_CONFLICT,
    TENANT_FORBIDDEN,
    USER_NOT_FOUND,
    VALIDATION_FAILED,
    api_error_response,
    error_response,
    is_retryable,
)
from api.server import app

API_KEY = "governance-test-key-123456"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)
    monkeypatch.delenv("SPECPROOF_MAX_JSON_BYTES", raising=False)


class FakeRedisRateLimit:
    def incr(self, key: str) -> int:
        return 1

    def expire(self, key: str, ttl: int) -> None:
        return None


class FakeMySQLStore:
    rows: dict[str, dict[str, Any]] = {}
    fail_next = False

    def create_job_with_outbox(self, job: dict[str, Any]) -> str:
        if FakeMySQLStore.fail_next:
            raise ConnectionError("mysql down")
        FakeMySQLStore.rows[job["id"]] = {**job, "status": "QUEUED"}
        return str(job["id"])

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return FakeMySQLStore.rows.get(job_id)

    def transition_job_status(self, job_id: str, to_status: str, **kw: Any) -> bool:
        row = FakeMySQLStore.rows.get(job_id)
        if row is None:
            return False
        row["status"] = to_status
        return True

    def record_audit(self, **kw: Any) -> None:
        return None

    def list_recent_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(FakeMySQLStore.rows.values())[-limit:]


@pytest.fixture()
def fake_mysql(monkeypatch: pytest.MonkeyPatch) -> FakeMySQLStore:
    FakeMySQLStore.rows = {}
    FakeMySQLStore.fail_next = False
    monkeypatch.setattr(jobs_module, "MySQLStore", FakeMySQLStore)
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedisRateLimit)
    return FakeMySQLStore()


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _payload() -> dict[str, Any]:
    return {
        "repo_path": "D:/experim/specproof-clean-clone-gate",
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec_path": "demo/requirement.txt",
        "depth": "FAST",
    }


# ── SSE: fake reader / probe / frame helpers ───────────────────────────────


class _FakeProgressReader:
    """In-memory stand-in for RedisStore's progress stream.

    from_id="0" returns the retained history; any other from_id returns
    the entries strictly after it (Redis XREAD exclusive semantics).
    """

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self.entries: list[dict[str, Any]] = entries if entries is not None else []

    def append(self, entry: dict[str, Any]) -> None:
        self.entries.append(dict(entry))

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100,
    ) -> list[dict[str, Any]]:
        if from_id == "0":
            return [dict(e) for e in self.entries[:count]]
        for index, entry in enumerate(self.entries):
            if entry["id"] == from_id:
                return [dict(e) for e in self.entries[index + 1:]][:count]
        return []


class _DisconnectProbe:
    """Fake request whose is_disconnected() flips after N polls."""

    def __init__(self, polls: int) -> None:
        self._calls = 0
        self._polls = polls

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls > self._polls


async def _no_sleep(_seconds: float) -> None:
    """Replace asyncio.sleep so the poll loop terminates instantly."""


def _seed_entries() -> _FakeProgressReader:
    reader = _FakeProgressReader()
    reader.append({
        "id": "10-0", "node": "intake", "status": "running",
        "percent": "10.0", "message": "started",
        "at": "2026-08-18T00:00:00+00:00",
    })
    reader.append({
        "id": "10-1", "node": "compile_contracts", "status": "running",
        "percent": "50.0", "message": "compiling",
        "at": "2026-08-18T00:00:01+00:00",
    })
    reader.append({
        "id": "10-2", "node": "publish_report", "status": "completed",
        "percent": "100.0", "message": "VERIFIED",
        "at": "2026-08-18T00:00:02+00:00",
    })
    return reader


async def _collect_frames(
    stream: AsyncGenerator[str, None], limit: int = 200,
) -> list[str]:
    frames: list[str] = []
    async for frame in stream:
        frames.append(frame)
        if len(frames) > limit:
            raise AssertionError("SSE stream did not terminate within frame limit")
    return frames


async def _drain_frames(stream: AsyncGenerator[str, None], count: int) -> list[str]:
    frames: list[str] = []
    for _ in range(count):
        frames.append(await anext(stream))
    return frames


def _parse_frames(frames: list[str]) -> list[tuple[str, str, dict[str, Any]]]:
    """Turn raw SSE frame strings into (event_id, event_type, payload)."""
    parsed: list[tuple[str, str, dict[str, Any]]] = []
    current_id = ""
    current_type = ""
    for frame in frames:
        if frame.startswith("id: "):
            current_id = frame[len("id: "):].strip()
        elif frame.startswith("event: "):
            current_type = frame[len("event: "):].strip()
        elif frame.startswith("data: "):
            parsed.append((current_id, current_type, json.loads(frame[len("data: "):])))
    return parsed


def _assert_progress_payload(payload: dict[str, Any], job_id: str) -> None:
    assert payload["job"] == job_id
    assert payload["type"] == "progress"
    assert isinstance(payload["stage"], str) and payload["stage"]
    assert payload["status"] in {"running", "completed"}
    assert 0.0 <= float(payload["percentage"]) <= 100.0
    assert payload["summary"]
    assert payload["ts"].startswith("2026-08-18T")


# ── SSE: sequence / resume / terminal idempotency ──────────────────────────


async def test_verify_sse_sequence_monotonic_and_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every progress event carries seq + type/stage/status/percentage/
    summary/ts; seq is strictly increasing across the full retained replay."""
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    reader = _seed_entries()
    stream = jobs_module._progress_stream("job-1", _DisconnectProbe(polls=1), reader, "0")
    frames = await _collect_frames(stream)
    parsed = _parse_frames(frames)
    assert len(parsed) == 3
    seqs = [payload["seq"] for _eid, _etype, payload in parsed]
    assert seqs == [1, 2, 3]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    for event_id, event_type, payload in parsed:
        assert event_id.startswith("10-")
        assert event_type == "progress"
        _assert_progress_payload(payload, "job-1")


async def test_verify_sse_resumes_after_last_event_id_and_replays_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Last-Event-ID resumes after exactly the acknowledged entry; the
    terminal event replays with an identical payload (idempotent repeat
    consumption); a stale id replays the full retained history."""
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    reader = _seed_entries()
    first = await _collect_frames(
        jobs_module._progress_stream("job-1", _DisconnectProbe(polls=1), reader, "0")
    )
    first_parsed = _parse_frames(first)
    terminal = first_parsed[-1]

    resumed = await _collect_frames(
        jobs_module._progress_stream("job-1", _DisconnectProbe(polls=2), reader, "10-1")
    )
    resumed_parsed = _parse_frames(resumed)
    assert [payload["seq"] for _eid, _etype, payload in resumed_parsed] == [3]
    assert resumed_parsed[0][2] == terminal[2]  # identical payload, same ts/seq

    stale = await _collect_frames(
        jobs_module._progress_stream("job-1", _DisconnectProbe(polls=1), reader, "999-9")
    )
    stale_parsed = _parse_frames(stale)
    assert [payload["seq"] for _eid, _etype, payload in stale_parsed] == [1, 2, 3]


async def test_verify_sse_live_entries_continue_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entries appended after the history replay keep the sequence going
    (seq is a stream rank, not a per-connection counter)."""
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    reader = _FakeProgressReader()
    reader.append({
        "id": "10-0", "node": "intake", "status": "running",
        "percent": "10.0", "message": "started",
        "at": "2026-08-18T00:00:00+00:00",
    })
    stream = jobs_module._progress_stream(
        "job-2", _DisconnectProbe(polls=3), reader, "0"
    )
    frames = await _drain_frames(stream, 3)  # id + event + data of entry 10-0
    reader.append({
        "id": "10-1", "node": "run_differential", "status": "completed",
        "percent": "100.0", "message": "VERIFIED",
        "at": "2026-08-18T00:00:05+00:00",
    })
    frames += await _collect_frames(stream)
    parsed = _parse_frames(frames)
    seqs = [payload["seq"] for _eid, _etype, payload in parsed]
    assert seqs == [1, 2]
    assert parsed[-1][2]["status"] == "completed"
    _assert_progress_payload(parsed[-1][2], "job-2")


# ── retryable derivation from the error-code failure class ────────────────


RETRYABLE_CASES: list[tuple[str, bool]] = [
    # Permanent for the same request (client/permission/not-found/conflict).
    (AUTH_REQUIRED, False),
    (TENANT_FORBIDDEN, False),
    (JOB_NOT_FOUND, False),
    (PAYLOAD_TOO_LARGE, False),
    (VALIDATION_FAILED, False),
    (STATE_CONFLICT, False),
    (USER_NOT_FOUND, False),
    # May succeed on a later attempt (degrade/execution-failure/rate-limit/internal).
    (PROVIDER_UNAVAILABLE, True),
    (EVIDENCE_UNVERIFIED, True),
    (RATE_LIMITED, True),
    (QUOTA_EXCEEDED, True),
    (INTERNAL, True),
]


@pytest.mark.parametrize("code,expected", RETRYABLE_CASES)
def test_retryable_derived_from_code_class(code: str, expected: bool) -> None:
    assert is_retryable(code) is expected
    body = error_response(422, code, "governance check")
    assert body["error"]["retryable"] is expected


def test_retryable_unknown_code_fails_closed() -> None:
    assert is_retryable("MYSTERY_CODE") is False
    body = error_response(500, "MYSTERY_CODE", "governance check")
    assert body["error"]["retryable"] is False


def test_retryable_keeps_detail_compatibility() -> None:
    original = "Job NOT accepted — persistence failed: mysql down"
    body = api_error_response(503, PROVIDER_UNAVAILABLE, original, "rid-1")
    assert body["detail"] == original
    assert body["error"]["message"] == original
    assert body["error"]["retryable"] is True


# ── Job creation allowlist ─────────────────────────────────────────────────


def test_job_create_allowlist_is_the_documented_set() -> None:
    assert frozenset(
        {"repo_path", "base_ref", "head_ref", "spec_path", "depth"}
    ) == jobs_module.JOB_CREATE_ALLOWLIST


UNKNOWN_FIELDS: list[tuple[str, Any]] = [
    ("command", "mvn clean test"),
    ("env", {"HOME": "/tmp", "PATH": "/bin"}),
    ("docker", {"image": "attacker/evil", "privileged": True}),
    ("output_path", "C:/Windows/System32/result.html"),
]


@pytest.mark.parametrize("field,value", UNKNOWN_FIELDS)
def test_job_create_rejects_unknown_field(
    field: str, value: Any, fake_mysql: FakeMySQLStore,
) -> None:
    """Arbitrary env/command/docker/output-path params are refused with
    422 VALIDATION_FAILED naming the offending field, and nothing is
    persisted."""
    client = TestClient(app)
    resp = client.post("/jobs", json={**_payload(), field: value}, headers=_headers())
    assert resp.status_code == 422
    body = resp.json()
    assert body["schema_version"] == 1
    assert body["error"]["code"] == VALIDATION_FAILED
    assert body["error"]["retryable"] is False  # client-class failure
    assert field in body["error"]["message"]  # offending field is named
    assert isinstance(body["detail"], list)  # legacy detail list preserved
    assert any(field in str(item.get("msg", "")) for item in body["detail"])
    assert FakeMySQLStore.rows == {}  # rejected before any persistence


def test_job_create_accepts_allowlisted_fields_only(fake_mysql: FakeMySQLStore) -> None:
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(), headers=_headers())
    assert resp.status_code == 202
    assert len(FakeMySQLStore.rows) == 1
