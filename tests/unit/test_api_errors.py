"""Unit tests for the §8.1 stable error-code table and error envelope.

Covers: code-table completeness, error_response/api_error_response shapes,
schema_version, backward-compatible detail preservation, and the wire
behavior of the key HTTP paths (401/404/409/413/422/503) through the
real app with faked stores.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.routes.jobs as jobs_module
from api.errors import (
    AUTH_REQUIRED,
    DEFAULT_CODE_BY_STATUS,
    ERROR_CODES,
    EVIDENCE_UNVERIFIED,
    INTERNAL,
    JOB_NOT_FOUND,
    PAYLOAD_TOO_LARGE,
    PROVIDER_UNAVAILABLE,
    QUOTA_EXCEEDED,
    RATE_LIMITED,
    SCHEMA_VERSION,
    STATE_CONFLICT,
    TENANT_FORBIDDEN,
    VALIDATION_FAILED,
    ApiError,
    api_error_response,
    error_response,
)
from api.server import app

API_KEY = "err-test-key-123456"

REQUIRED_CODES = [
    AUTH_REQUIRED,
    TENANT_FORBIDDEN,
    QUOTA_EXCEEDED,
    JOB_NOT_FOUND,
    PROVIDER_UNAVAILABLE,
    EVIDENCE_UNVERIFIED,
    RATE_LIMITED,
    PAYLOAD_TOO_LARGE,
    VALIDATION_FAILED,
    INTERNAL,
]


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
        return job["id"]

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


def _assert_envelope(body: dict[str, Any], code: str, detail_fragment: str) -> None:
    assert body["schema_version"] == SCHEMA_VERSION == 1
    assert body["error"]["code"] == code
    assert detail_fragment in body["error"]["message"]
    assert detail_fragment in body["detail"]  # legacy key preserved verbatim
    assert re.fullmatch(r"[0-9a-f]{16}", body["error"]["request_id"])


# ── Code table ─────────────────────────────────────────────────────────────


def test_code_table_contains_all_required_codes() -> None:
    assert set(REQUIRED_CODES) <= set(ERROR_CODES)


def test_code_table_statuses_are_valid_http() -> None:
    for code, status in ERROR_CODES.items():
        assert 100 <= status <= 599, code


def test_default_code_by_status_covers_key_paths() -> None:
    assert DEFAULT_CODE_BY_STATUS[401] == AUTH_REQUIRED
    assert DEFAULT_CODE_BY_STATUS[403] == TENANT_FORBIDDEN
    assert DEFAULT_CODE_BY_STATUS[404] == JOB_NOT_FOUND
    assert DEFAULT_CODE_BY_STATUS[409] == STATE_CONFLICT
    assert DEFAULT_CODE_BY_STATUS[413] == PAYLOAD_TOO_LARGE
    assert DEFAULT_CODE_BY_STATUS[422] == VALIDATION_FAILED
    assert DEFAULT_CODE_BY_STATUS[429] == RATE_LIMITED
    assert DEFAULT_CODE_BY_STATUS[500] == INTERNAL
    assert DEFAULT_CODE_BY_STATUS[503] == PROVIDER_UNAVAILABLE


def test_code_table_canonical_statuses() -> None:
    assert ERROR_CODES[AUTH_REQUIRED] == 401
    assert ERROR_CODES[TENANT_FORBIDDEN] == 403
    assert ERROR_CODES[JOB_NOT_FOUND] == 404
    assert ERROR_CODES[STATE_CONFLICT] == 409
    assert ERROR_CODES[PAYLOAD_TOO_LARGE] == 413
    assert ERROR_CODES[VALIDATION_FAILED] == 422
    assert ERROR_CODES[INTERNAL] == 500
    assert ERROR_CODES[PROVIDER_UNAVAILABLE] == 503


# ── Helper shapes ──────────────────────────────────────────────────────────


def test_error_response_shape() -> None:
    body = error_response(404, JOB_NOT_FOUND, "Job nope not found", "abc123def4567890")
    assert set(body) == {"error", "schema_version"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == JOB_NOT_FOUND
    assert body["error"]["message"] == "Job nope not found"
    assert body["error"]["request_id"] == "abc123def4567890"
    assert body["schema_version"] == SCHEMA_VERSION == 1


def test_error_response_generates_request_id_when_missing() -> None:
    body = error_response(503, PROVIDER_UNAVAILABLE, "down")
    assert re.fullmatch(r"[0-9a-f]{16}", body["error"]["request_id"])


def test_api_error_response_preserves_legacy_detail() -> None:
    original = "Job NOT accepted — persistence failed: mysql down"
    body = api_error_response(503, PROVIDER_UNAVAILABLE, original, "rid-1")
    assert body["detail"] == original
    assert body["error"]["message"] == original
    assert body["error"]["code"] == PROVIDER_UNAVAILABLE
    assert body["schema_version"] == 1


def test_api_error_is_an_http_exception_with_code() -> None:
    err = ApiError(status_code=404, code=JOB_NOT_FOUND, detail="x")
    assert isinstance(err, HTTPException)
    assert err.status_code == 404
    assert err.detail == "x"
    assert err.error_code == JOB_NOT_FOUND


# ── Wire behavior (real app, faked stores) ─────────────────────────────────


def test_404_job_not_found_wire(fake_mysql: FakeMySQLStore) -> None:
    client = TestClient(app)
    resp = client.get("/jobs/00000000-0000-0000-0000-000000000000", headers=_headers())
    assert resp.status_code == 404
    body = resp.json()
    _assert_envelope(body, JOB_NOT_FOUND, "not found")
    assert body["error"]["request_id"] == resp.headers["X-Request-ID"]


def test_401_auth_required_wire(fake_mysql: FakeMySQLStore) -> None:
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload())
    assert resp.status_code == 401
    _assert_envelope(resp.json(), AUTH_REQUIRED, "Invalid or missing API key")


def test_409_state_conflict_wire(fake_mysql: FakeMySQLStore) -> None:
    client = TestClient(app)
    created = client.post("/jobs", json=_payload(), headers=_headers()).json()
    FakeMySQLStore.rows[created["job_id"]]["status"] = "VERIFIED"
    resp = client.post("/jobs/" + created["job_id"] + "/cancel", headers=_headers())
    assert resp.status_code == 409
    _assert_envelope(resp.json(), STATE_CONFLICT, "cannot cancel")


def test_413_payload_too_large_wire(
    fake_mysql: FakeMySQLStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "1024")
    client = TestClient(app)
    resp = client.post("/jobs", json={"repo_path": "x" * 2048})
    assert resp.status_code == 413
    body = resp.json()
    _assert_envelope(body, PAYLOAD_TOO_LARGE, "1024 bytes")
    assert body["error"]["request_id"] == resp.headers["X-Request-ID"]


def test_422_validation_failed_wire(fake_mysql: FakeMySQLStore) -> None:
    client = TestClient(app)
    resp = client.post("/jobs", json={"repo_path": ""}, headers=_headers())
    assert resp.status_code == 422
    body = resp.json()
    assert body["schema_version"] == 1
    assert body["error"]["code"] == VALIDATION_FAILED
    assert isinstance(body["detail"], list)  # legacy FastAPI error list kept
    assert any("repo_path" in str(item.get("loc", [])) for item in body["detail"])


def test_503_provider_unavailable_wire(fake_mysql: FakeMySQLStore) -> None:
    FakeMySQLStore.fail_next = True
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(), headers=_headers())
    assert resp.status_code == 503
    _assert_envelope(resp.json(), PROVIDER_UNAVAILABLE, "NOT accepted")


def test_evidence_unverified_code_on_missing_artifact(
    fake_mysql: FakeMySQLStore,
) -> None:
    import api.routes.web as web_module

    FakeMySQLStore.rows["j-1"] = {"id": "j-1", "status": "VERIFIED"}
    mp = pytest.MonkeyPatch()
    mp.setattr(web_module, "MySQLStore", FakeMySQLStore)
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/jobs/j-1/certificate", headers=_headers())
        assert resp.status_code == 404
        _assert_envelope(resp.json(), EVIDENCE_UNVERIFIED, "No merge-certificate")
    finally:
        mp.undo()
