"""API tests for the job submission / query endpoints (B12 + P0-A2 auth).

The MySQL store is faked at the route level — these tests prove the HTTP
contract (202 on success, 503 when persistence fails, 404 for unknown
jobs) AND the security contract (401 without a key, 503 when no key is
configured) without needing a live database.
"""


import pytest
from fastapi.testclient import TestClient

import api.routes.jobs as jobs_module
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
    """In-memory stand-in for the route handlers."""

    rows: dict = {}
    fail_next = False

    def create_job_with_outbox(self, job):
        if FakeMySQLStore.fail_next:
            raise ConnectionError("mysql down")
        FakeMySQLStore.rows[job["id"]] = {
            "id": job["id"],
            "repo_path": job["repo_path"],
            "base_ref": job["base_ref"],
            "head_ref": job["head_ref"],
            "spec_path": job["spec_path"],
            "depth": job["depth"],
            "status": "QUEUED",
        }
        return job["id"]

    def get_job(self, job_id):
        return FakeMySQLStore.rows.get(job_id)

    def transition_job_status(self, job_id, to_status, **kwargs):
        row = FakeMySQLStore.rows.get(job_id)
        if row is None:
            return False
        row["status"] = to_status
        return True

    def record_audit(self, **kwargs):
        pass

    def list_recent_jobs(self, limit=50):
        items = list(FakeMySQLStore.rows.values())
        return items[-limit:]

    def search_jobs(self, limit=50, offset=0, status=None, query=""):
        del status, query
        items = list(FakeMySQLStore.rows.values())
        return {"jobs": items[offset:offset + limit], "total": len(items),
                "limit": limit, "offset": offset}


@pytest.fixture()
def fake_mysql(monkeypatch):
    FakeMySQLStore.rows = {}
    FakeMySQLStore.fail_next = False
    monkeypatch.setattr(jobs_module, "MySQLStore", FakeMySQLStore)
    # Rate limiter imports RedisStore at call time from storage.redis;
    # fake it there so tests don't need a live instance.
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedisRateLimit)
    yield FakeMySQLStore


def _headers():
    return {"X-API-Key": API_KEY}


def _payload():
    return {
        "repo_path": "D:/experim/specproof-clean-clone-gate",
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec_path": "demo/requirement.txt",
        "depth": "FAST",
    }


def test_create_job_returns_202_with_id(fake_mysql):
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(), headers=_headers())
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "QUEUED"
    assert body["job_id"] in FakeMySQLStore.rows


def test_create_job_401_without_key(fake_mysql):
    """P0-A2: the job API must fail closed without a valid key."""
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload())
    assert resp.status_code == 401


def test_create_job_401_with_wrong_key(fake_mysql):
    client = TestClient(app)
    resp = client.post(
        "/jobs", json=_payload(), headers={"X-API-Key": "wrong-key"}
    )
    assert resp.status_code == 401


def test_create_job_503_when_key_unconfigured(fake_mysql, monkeypatch):
    """P0-A2: no configured key must NEVER mean open access."""
    monkeypatch.setenv("SPECPROOF_API_KEY", "")
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload())
    assert resp.status_code == 503


def test_create_job_503_when_persistence_fails(fake_mysql):
    """The API must never accept a job it could not persist."""
    FakeMySQLStore.fail_next = True
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(), headers=_headers())
    assert resp.status_code == 503
    assert "NOT accepted" in resp.json()["detail"]


def test_create_job_validates_payload(fake_mysql):
    client = TestClient(app)
    resp = client.post(
        "/jobs", json={"repo_path": ""}, headers=_headers()
    )
    assert resp.status_code == 422


def test_get_job_returns_row(fake_mysql):
    client = TestClient(app)
    created = client.post(
        "/jobs", json=_payload(), headers=_headers()
    ).json()
    resp = client.get(
        "/jobs/" + created["job_id"], headers=_headers()
    )
    assert resp.status_code == 200
    assert resp.json()["job"]["status"] == "QUEUED"


def test_get_job_unknown_returns_404(fake_mysql):
    client = TestClient(app)
    resp = client.get(
        "/jobs/00000000-0000-0000-0000-000000000000", headers=_headers()
    )
    assert resp.status_code == 404


def test_list_jobs_returns_all(fake_mysql):
    client = TestClient(app)
    for _ in range(3):
        client.post("/jobs", json=_payload(), headers=_headers())
    resp = client.get("/jobs", headers=_headers())
    assert resp.status_code == 200
    assert len(resp.json()["jobs"]) == 3


@pytest.mark.parametrize("limit", [0, -1, 201, 100000])
def test_list_jobs_rejects_unbounded_queries(fake_mysql, limit):
    client = TestClient(app)
    response = client.get(f"/jobs?limit={limit}", headers=_headers())
    assert response.status_code == 422


def test_submission_trims_copied_paths_and_rejects_blank_values(fake_mysql):
    client = TestClient(app)
    payload = {**_payload(), "repo_path": "  D:/my-project  ", "base_ref": " main "}
    response = client.post("/jobs", json=payload, headers=_headers())
    assert response.status_code == 202
    row = FakeMySQLStore.rows[response.json()["job_id"]]
    assert row["repo_path"] == "D:/my-project"
    assert row["base_ref"] == "main"
    for field in ("repo_path", "base_ref", "head_ref", "spec_path"):
        response = client.post("/jobs", json={**_payload(), field: "   "}, headers=_headers())
        assert response.status_code == 422


def test_submission_rejects_path_longer_than_database_column(fake_mysql):
    response = TestClient(app).post(
        "/jobs", json={**_payload(), "repo_path": "a" * 513}, headers=_headers(),
    )
    assert response.status_code == 422
    assert not FakeMySQLStore.rows


def test_cancel_queued_job(fake_mysql):
    client = TestClient(app)
    created = client.post(
        "/jobs", json=_payload(), headers=_headers()
    ).json()
    resp = client.post(
        "/jobs/" + created["job_id"] + "/cancel", headers=_headers()
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "CANCELLED"
    assert FakeMySQLStore.rows[created["job_id"]]["status"] == "CANCELLED"


def test_cancel_terminal_job_conflicts(fake_mysql):
    client = TestClient(app)
    created = client.post(
        "/jobs", json=_payload(), headers=_headers()
    ).json()
    FakeMySQLStore.rows[created["job_id"]]["status"] = "VERIFIED"
    resp = client.post(
        "/jobs/" + created["job_id"] + "/cancel", headers=_headers()
    )
    assert resp.status_code == 409


def test_progress_endpoint_requires_key(fake_mysql):
    client = TestClient(app)
    resp = client.get("/jobs/abc/progress")
    assert resp.status_code == 401


def test_health_endpoint_open_and_ok(monkeypatch):
    class FakeRedis:
        def is_ready(self):
            return True

    class FakeMySQL:
        def is_ready(self):
            return True

    # api.server.health() imports the stores at call time.
    monkeypatch.setattr("storage.redis.RedisStore", FakeRedis)
    monkeypatch.setattr("storage.mysql.MySQLStore", FakeMySQL)
    monkeypatch.setenv("SPECPROOF_AGENT_JOBS_URL", "sqlite:.local/light-jobs.sqlite3")
    client = TestClient(app)
    resp = client.get("/health")  # no key needed for liveness
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_reports_degraded_when_mysql_is_down(monkeypatch):
    """A job-store outage must not be reported as a healthy stack."""

    class DeadRedis:
        def is_ready(self):
            return False

    class DeadMySQL:
        def is_ready(self):
            return False

    monkeypatch.setattr("storage.redis.RedisStore", DeadRedis)
    monkeypatch.setattr("storage.mysql.MySQLStore", DeadMySQL)
    monkeypatch.setenv("SPECPROOF_AGENT_JOBS_URL", "sqlite:.local/light-jobs.sqlite3")
    client = TestClient(app)
    resp = client.get("/health")
    # Still 200: readiness pollers must keep working while a dependency is down.
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["mysql"] is False
    assert body["redis"] is False
