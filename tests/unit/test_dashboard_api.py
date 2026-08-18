"""Dashboard / summary / metrics API tests (fake stores, auth enforced)."""

import pytest
from fastapi.testclient import TestClient

import api.routes.jobs as jobs_module
from api.server import app

API_KEY = "dash-test-key"


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
    summaries: dict = {}

    def create_job_with_outbox(self, job):
        FakeMySQLStore.rows[job["id"]] = {**job, "status": "QUEUED"}
        return job["id"]

    def get_job(self, job_id):
        return FakeMySQLStore.rows.get(job_id)

    def get_job_summary(self, job_id):
        return FakeMySQLStore.summaries.get(job_id)

    def list_recent_jobs(self, limit=50):
        return list(FakeMySQLStore.rows.values())[-limit:]

    def transition_job_status(self, job_id, to_status, **kwargs):
        row = FakeMySQLStore.rows.get(job_id)
        if row is None:
            return False
        row["status"] = to_status
        return True

    def record_audit(self, **kwargs):
        pass


@pytest.fixture()
def fakes(monkeypatch):
    FakeMySQLStore.rows = {}
    FakeMySQLStore.summaries = {}
    monkeypatch.setattr(jobs_module, "MySQLStore", FakeMySQLStore)
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedisRateLimit)
    yield


def _headers():
    return {"X-API-Key": API_KEY}


def test_summary_endpoint_returns_persisted(fakes):
    FakeMySQLStore.rows["j-1"] = {"id": "j-1", "status": "BLOCKED"}
    FakeMySQLStore.summaries["j-1"] = {
        "verdict": "BLOCKED",
        "matrix_failed": 1,
        "findings": [{"severity": "BLOCKER", "contract_id": "AUTH-01"}],
    }
    client = TestClient(app)
    resp = client.get("/jobs/j-1/summary", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["summary"]["verdict"] == "BLOCKED"
    assert len(resp.json()["summary"]["findings"]) == 1


def test_summary_endpoint_404_unknown(fakes):
    client = TestClient(app)
    resp = client.get("/jobs/nope/summary", headers=_headers())
    assert resp.status_code == 404


def test_summary_endpoint_requires_key(fakes):
    client = TestClient(app)
    resp = client.get("/jobs/j-1/summary")
    assert resp.status_code == 401


def test_dashboard_served_without_key():
    client = TestClient(app)
    resp = client.get("/dashboard/static/index.html")
    assert resp.status_code == 200
    assert "SpecProof Dashboard" in resp.text


def test_metrics_endpoint_served():
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "specproof_http_requests_total" in resp.text
