"""Backlog #9: envelope retryable field + SSE sequence / retention tests.

Covers the three contracts of the backlog item:

1. The §8.1 error envelope derives `retryable` from the failure class:
   client/permission/not-found/conflict are permanent, while
   degrade/execution-failure/rate-limit/internal may succeed on retry;
   unknown codes fail closed. The legacy envelope fields stay unchanged
   and `retryable` is appended as a plain boolean.
2. Progress-stream entries carry an absolute per-job `sequence` (atomic
   Redis INCR counter) that stays monotonic across MAXLEN trims, while
   the retained-window rank `seq` keeps its legacy semantics.
3. The retention policy is explicit and configurable (XADD MAXLEN + key
   TTL) and is enforced on every write against a fake Redis client.
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
    ERROR_CLASS_BY_CODE,
    ERROR_CODES,
    EVIDENCE_UNVERIFIED,
    INTERNAL,
    JOB_NOT_FOUND,
    PAYLOAD_TOO_LARGE,
    PROVIDER_UNAVAILABLE,
    QUOTA_EXCEEDED,
    RATE_LIMITED,
    RETRYABLE_CLASSES,
    SCHEMA_VERSION,
    STATE_CONFLICT,
    TENANT_FORBIDDEN,
    USER_NOT_FOUND,
    VALIDATION_FAILED,
    api_error_response,
    error_response,
    is_retryable,
)
from api.server import app
from storage.redis import (
    STREAM_DEFAULT_MAXLEN,
    STREAM_DEFAULT_TTL_SECONDS,
    RedisConfig,
    RedisStore,
)

API_KEY = "envelope-retryable-test-key-123456"


# ── Envelope retryable: classification and wire shape ────────────────────────────────────


RETRYABLE_TRUE_CODES = [
    PROVIDER_UNAVAILABLE,
    EVIDENCE_UNVERIFIED,
    RATE_LIMITED,
    QUOTA_EXCEEDED,
    INTERNAL,
]

RETRYABLE_FALSE_CODES = [
    AUTH_REQUIRED,
    TENANT_FORBIDDEN,
    JOB_NOT_FOUND,
    PAYLOAD_TOO_LARGE,
    VALIDATION_FAILED,
    STATE_CONFLICT,
    USER_NOT_FOUND,
]


@pytest.mark.parametrize("code", RETRYABLE_TRUE_CODES)
def test_envelope_retryable_true_for_retryable_classes(code: str) -> None:
    assert is_retryable(code) is True
    assert error_response(503, code, "boom")["error"]["retryable"] is True


@pytest.mark.parametrize("code", RETRYABLE_FALSE_CODES)
def test_envelope_retryable_false_for_permanent_classes(code: str) -> None:
    assert is_retryable(code) is False
    assert error_response(422, code, "nope")["error"]["retryable"] is False


def test_every_error_code_has_a_failure_class() -> None:
    assert set(ERROR_CLASS_BY_CODE) == set(ERROR_CODES)


def test_failure_classes_use_only_documented_vocabulary() -> None:
    documented = {
        "client",
        "permission",
        "not-found",
        "conflict",
        "rate-limit",
        "degrade",
        "execution-failure",
        "internal",
    }
    assert set(ERROR_CLASS_BY_CODE.values()) <= documented


def test_retryable_classes_are_the_documented_set() -> None:
    assert frozenset(
        {"degrade", "execution-failure", "rate-limit", "internal"}
    ) == RETRYABLE_CLASSES


def test_retryable_agrees_with_class_table_for_every_code() -> None:
    for code in ERROR_CODES:
        expected = ERROR_CLASS_BY_CODE[code] in RETRYABLE_CLASSES
        assert is_retryable(code) is expected, code


def test_unknown_code_fails_closed() -> None:
    assert is_retryable("MYSTERY_CODE") is False
    assert error_response(500, "MYSTERY_CODE", "x")["error"]["retryable"] is False


def test_envelope_shape_legacy_fields_unchanged_retryable_appended() -> None:
    body = error_response(404, JOB_NOT_FOUND, "Job nope not found", "abc123def4567890")
    assert set(body) == {"error", "schema_version"}
    assert set(body["error"]) == {"code", "message", "request_id", "retryable"}
    assert body["error"]["code"] == JOB_NOT_FOUND
    assert body["error"]["message"] == "Job nope not found"
    assert body["error"]["request_id"] == "abc123def4567890"
    assert isinstance(body["error"]["retryable"], bool)
    assert body["error"]["retryable"] is False
    assert body["schema_version"] == SCHEMA_VERSION == 1


def test_api_error_response_preserves_legacy_detail_and_retryable() -> None:
    original = "Job NOT accepted — persistence failed: mysql down"
    body = api_error_response(503, PROVIDER_UNAVAILABLE, original, "rid-1")
    assert body["detail"] == original
    assert body["error"]["message"] == original
    assert body["error"]["request_id"] == "rid-1"
    assert body["error"]["retryable"] is True


# ── Envelope retryable on the wire (real app, faked stores) ───────────────────


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


def test_wire_503_provider_unavailable_is_retryable(fake_mysql: FakeMySQLStore) -> None:
    FakeMySQLStore.fail_next = True
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(), headers=_headers())
    assert resp.status_code == 503
    assert resp.json()["error"]["retryable"] is True


def test_wire_404_job_not_found_is_not_retryable(fake_mysql: FakeMySQLStore) -> None:
    client = TestClient(app)
    resp = client.get(
        "/jobs/00000000-0000-0000-0000-000000000000", headers=_headers()
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["retryable"] is False


def test_wire_409_state_conflict_is_not_retryable(fake_mysql: FakeMySQLStore) -> None:
    client = TestClient(app)
    created = client.post("/jobs", json=_payload(), headers=_headers()).json()
    FakeMySQLStore.rows[created["job_id"]]["status"] = "VERIFIED"
    resp = client.post("/jobs/" + created["job_id"] + "/cancel", headers=_headers())
    assert resp.status_code == 409
    assert resp.json()["error"]["retryable"] is False


# ── SSE: store-level sequence counter and retention policy ──────────────────


class RecordingRedis:
    """Fake Redis client recording INCR/EXPIRE/XADD calls."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.xadd_calls: list[tuple[str, dict[str, Any], int]] = []
        self.expire_calls: list[tuple[str, int]] = []

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))

    def xadd(self, key: str, data: dict[str, Any], maxlen: int | None = None) -> str:
        self.xadd_calls.append((key, dict(data), int(maxlen or 0)))
        return f"{1700000000000 + len(self.xadd_calls)}-0"


def _store_with(rec: RecordingRedis, config: RedisConfig | None = None) -> RedisStore:
    store = RedisStore(config=config) if config is not None else RedisStore()
    store._client = rec  # noqa: SLF001 — test seam, mirrors test_redis_stream.py
    return store


def test_xadd_progress_stores_monotonic_per_job_sequence() -> None:
    rec = RecordingRedis()
    store = _store_with(rec)
    first = store.xadd_progress("job-1", "intake", "running", "start", 10.0)
    second = store.xadd_progress("job-1", "compile", "running", "compiling", 50.0)
    assert rec.counters["specproof:stream:job:job-1:seq"] == 2
    assert rec.xadd_calls[0][1]["seq"] == "1"
    assert rec.xadd_calls[1][1]["seq"] == "2"
    assert first != second


def test_sequence_counter_is_isolated_per_job() -> None:
    rec = RecordingRedis()
    store = _store_with(rec)
    store.xadd_progress("job-a", "intake", "running")
    store.xadd_progress("job-a", "compile", "running")
    store.xadd_progress("job-b", "intake", "running")
    assert rec.counters["specproof:stream:job:job-a:seq"] == 2
    assert rec.counters["specproof:stream:job:job-b:seq"] == 1


def test_retention_policy_defaults_maxlen_and_ttl() -> None:
    assert RedisStore.STREAM_MAXLEN == STREAM_DEFAULT_MAXLEN == 1000
    assert RedisStore.STREAM_TTL_SECONDS == STREAM_DEFAULT_TTL_SECONDS == 86400
    rec = RecordingRedis()
    _store_with(rec).xadd_progress("job-1", "intake", "running")
    assert rec.xadd_calls[0][2] == 1000
    assert ("specproof:stream:job:job-1", 86400) in rec.expire_calls
    assert ("specproof:stream:job:job-1:seq", 86400) in rec.expire_calls


def test_retention_policy_follows_config_override() -> None:
    rec = RecordingRedis()
    store = _store_with(rec, RedisConfig(stream_maxlen=50, stream_ttl_seconds=3600))
    store.xadd_progress("job-1", "intake", "running")
    assert rec.xadd_calls[0][2] == 50
    assert all(ttl == 3600 for _key, ttl in rec.expire_calls)


def test_retention_policy_reads_env_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_STREAM_MAXLEN", "250")
    monkeypatch.setenv("REDIS_STREAM_TTL_SECONDS", "1800")
    config = RedisConfig.from_env()
    assert config.stream_maxlen == 250
    assert config.stream_ttl_seconds == 1800
    rec = RecordingRedis()
    _store_with(rec, config).xadd_progress("job-1", "intake", "running")
    assert rec.xadd_calls[0][2] == 250
    assert all(ttl == 1800 for _key, ttl in rec.expire_calls)


class FixedXreadRedis:
    """Fake client returning one canned stream entry."""

    def __init__(self, fields: dict[str, str]) -> None:
        self._fields = fields

    def xread(self, streams: dict[str, str], count: int | None = None) -> Any:
        return [("specproof:stream:job:test", [("10-0", self._fields)])]


def test_xread_progress_returns_absolute_sequence() -> None:
    fields = {
        "seq": "7",
        "node": "intake",
        "status": "running",
        "at": "2026-08-18T00:00:00+00:00",
        "percent": "10",
        "message": "started",
    }
    store = RedisStore()
    store._client = FixedXreadRedis(fields)  # noqa: SLF001
    events = store.xread_progress("test", "0", 10)
    assert len(events) == 1
    assert events[0]["sequence"] == 7
    assert events[0]["node"] == "intake"


def test_xread_progress_legacy_entry_without_counter_has_zero_sequence() -> None:
    fields = {
        "node": "intake",
        "status": "running",
        "at": "2026-08-18T00:00:00+00:00",
        "percent": "10",
        "message": "started",
    }
    store = RedisStore()
    store._client = FixedXreadRedis(fields)  # noqa: SLF001
    events = store.xread_progress("test", "0", 10)
    assert events[0]["sequence"] == 0


# ── SSE: route payload and reconnect behavior ──────────────────────────────


def test_progress_payload_adds_absolute_sequence_and_keeps_rank() -> None:
    payload = jobs_module._progress_payload("job-1", 3, {"sequence": 42})
    assert payload["seq"] == 3
    assert payload["sequence"] == 42
    assert payload["job"] == "job-1"


def test_progress_payload_falls_back_to_rank_for_legacy_entries() -> None:
    payload = jobs_module._progress_payload("job-1", 7, {})
    assert payload["seq"] == 7
    assert payload["sequence"] == 7


class SequenceReader:
    """In-memory reader whose entries carry absolute sequence numbers."""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = [dict(e) for e in entries]

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100,
    ) -> list[dict[str, Any]]:
        if from_id == "0":
            return [dict(e) for e in self.entries[:count]]
        for index, entry in enumerate(self.entries):
            if entry["id"] == from_id:
                return [dict(e) for e in self.entries[index + 1:]][:count]
        return []


class DisconnectProbe:
    """Fake request whose is_disconnected() flips after N polls."""

    def __init__(self, polls: int) -> None:
        self._calls = 0
        self._polls = polls

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls > self._polls


async def _no_sleep(_seconds: float) -> None:
    """Replace asyncio.sleep so the poll loop terminates instantly."""


def _entry(entry_id: str, sequence: int, status: str = "running") -> dict[str, Any]:
    return {
        "id": entry_id,
        "sequence": sequence,
        "node": "intake",
        "status": status,
        "percent": "10.0",
        "message": "started",
        "at": "2026-08-18T00:00:00+00:00",
    }


async def _collect_frames(
    stream: AsyncGenerator[str, None], limit: int = 100,
) -> list[str]:
    frames: list[str] = []
    async for frame in stream:
        frames.append(frame)
        if len(frames) > limit:
            raise AssertionError("SSE stream did not terminate within frame limit")
    return frames


def _payloads(frames: list[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for frame in frames:
        if frame.startswith("data: "):
            payloads.append(json.loads(frame[len("data: "):]))
    return payloads


async def test_stream_sequence_is_absolute_and_rank_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    reader = SequenceReader([
        _entry("10-0", 10),
        _entry("10-1", 11),
        _entry("10-2", 12, "completed"),
    ])
    stream = jobs_module._progress_stream("job-1", DisconnectProbe(1), reader, "0")
    payloads = _payloads(await _collect_frames(stream))
    assert [p["seq"] for p in payloads] == [1, 2, 3]
    assert [p["sequence"] for p in payloads] == [10, 11, 12]
    assert [p["sequence"] for p in payloads] == sorted(
        p["sequence"] for p in payloads
    )


async def test_stream_resume_sequence_survives_window_trim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After MAXLEN dropped the oldest entry the rank (seq) renumbers, but
    the absolute sequence lets a reconnecting client dedupe and re-order."""
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    reader = SequenceReader([
        _entry("10-1", 11),
        _entry("10-2", 12, "completed"),
    ])
    stream = jobs_module._progress_stream(
        "job-1", DisconnectProbe(1), reader, "10-1"
    )
    payloads = _payloads(await _collect_frames(stream))
    assert [p["seq"] for p in payloads] == [2]
    assert [p["sequence"] for p in payloads] == [12]


async def test_stream_stale_id_replays_retained_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    reader = SequenceReader([_entry("10-0", 10), _entry("10-1", 11)])
    stream = jobs_module._progress_stream("job-1", DisconnectProbe(1), reader, "999-9")
    payloads = _payloads(await _collect_frames(stream))
    assert [p["seq"] for p in payloads] == [1, 2]
    assert [p["sequence"] for p in payloads] == [10, 11]
