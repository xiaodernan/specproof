"""API tests for the finding feedback endpoints (Go/No-Go #13 mechanism).

FakeMySQLStore at the route level — proves the HTTP contract (201 on
persisted accept, 404 for unknown jobs, 503 when storage fails) and the
security contract (401 without an API key) without a live database.
"""

import pytest
from fastapi.testclient import TestClient

import api.routes.feedback as feedback_module
from api.server import app

API_KEY = "test-api-key-123456"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)


class FakeRedisRateLimit:
    def incr(self, key):
        return 1

    def expire(self, key, ttl):
        pass


class FakeMySQLStore:
    rows: dict = {}
    feedback_rows: list = []
    fail_next = False

    def get_job(self, job_id):
        return FakeMySQLStore.rows.get(job_id)

    def insert_feedback(self, feedback):
        if FakeMySQLStore.fail_next:
            raise ConnectionError("mysql down")
        FakeMySQLStore.feedback_rows.append(feedback)

    def list_feedback(self, job_id):
        return [r for r in FakeMySQLStore.feedback_rows if r["job_id"] == job_id]

    def feedback_stats(self, job_id):
        accepted = sum(
            1 for r in FakeMySQLStore.feedback_rows
            if r["job_id"] == job_id and r["verdict"] == "accept"
        )
        rejected = sum(
            1 for r in FakeMySQLStore.feedback_rows
            if r["job_id"] == job_id and r["verdict"] == "reject"
        )
        total = accepted + rejected
        return {
            "job_id": job_id, "accepted": accepted, "rejected": rejected,
            "no_feedback_not_counted": True,
            "acceptance_rate_pct": (
                round(100.0 * accepted / total, 1) if total else None
            ),
        }


@pytest.fixture()
def fake_mysql(monkeypatch):
    FakeMySQLStore.rows = {}
    FakeMySQLStore.feedback_rows = []
    FakeMySQLStore.fail_next = False
    monkeypatch.setattr(feedback_module, "MySQLStore", FakeMySQLStore)
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedisRateLimit)
    yield FakeMySQLStore


def _client() -> TestClient:
    return TestClient(app)


def test_feedback_requires_api_key():
    client = TestClient(app)
    resp = client.post("/api/v1/jobs/j-1/feedback", json={
        "finding_id": "f-1", "contract_id": "AUTH-01",
        "severity": "BLOCKER", "verdict": "accept", "created_by": "u1",
    })
    assert resp.status_code == 401


def test_accept_recorded_201(fake_mysql):
    fake_mysql.rows["j-1"] = {"id": "j-1", "tenant_id": None}
    client = _client()
    resp = client.post("/api/v1/jobs/j-1/feedback", headers={
        "X-API-Key": API_KEY,
    }, json={
        "finding_id": "f-1", "contract_id": "AUTH-01",
        "severity": "BLOCKER", "verdict": "accept", "created_by": "u1",
    })
    assert resp.status_code == 201
    assert resp.json()["verdict"] == "accept"
    assert len(fake_mysql.feedback_rows) == 1


def test_stats_rate_and_unknown_job_404(fake_mysql):
    fake_mysql.rows["j-1"] = {"id": "j-1", "tenant_id": None}
    client = _client()
    for verdict in ("accept", "accept", "reject"):
        resp = client.post("/api/v1/jobs/j-1/feedback", headers={
            "X-API-Key": API_KEY,
        }, json={
            "finding_id": "f-" + verdict, "contract_id": "AUTH-01",
            "severity": "BLOCKER", "verdict": verdict, "created_by": "u1",
        })
        assert resp.status_code == 201
    data = client.get("/api/v1/jobs/j-1/feedback", headers={
        "X-API-Key": API_KEY,
    }).json()
    assert data["stats"]["acceptance_rate_pct"] == 66.7
    assert data["stats"]["no_feedback_not_counted"] is True
    unknown = client.get("/api/v1/jobs/nope/feedback", headers={
        "X-API-Key": API_KEY,
    })
    assert unknown.status_code == 404


def test_invalid_verdict_422(fake_mysql):
    fake_mysql.rows["j-1"] = {"id": "j-1", "tenant_id": None}
    client = _client()
    resp = client.post("/api/v1/jobs/j-1/feedback", headers={
        "X-API-Key": API_KEY,
    }, json={
        "finding_id": "f-1", "contract_id": "AUTH-01",
        "severity": "BLOCKER", "verdict": "maybe", "created_by": "u1",
    })
    assert resp.status_code == 422
    assert fake_mysql.feedback_rows == []


def test_storage_failure_503(fake_mysql):
    fake_mysql.rows["j-1"] = {"id": "j-1", "tenant_id": None}
    fake_mysql.fail_next = True
    client = _client()
    resp = client.post("/api/v1/jobs/j-1/feedback", headers={
        "X-API-Key": API_KEY,
    }, json={
        "finding_id": "f-1", "contract_id": "AUTH-01",
        "severity": "BLOCKER", "verdict": "accept", "created_by": "u1",
    })
    assert resp.status_code == 503
