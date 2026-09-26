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
    """Mirrors MySQLStore's feedback methods — including their shapes.

    ``insert_feedback`` returns {"state", "id"} and enforces one row per
    (finding_id, created_by), because production does: the route echoes
    ``state`` to the browser, and a fake that appended every POST would
    model the pre-0012 double-counting bug instead of the fixed behaviour.
    """

    rows: dict = {}
    feedback_rows: list = []
    fail_next = False

    def get_job(self, job_id):
        return FakeMySQLStore.rows.get(job_id)

    @staticmethod
    def _existing(feedback):
        for row in FakeMySQLStore.feedback_rows:
            if (row["finding_id"], row["created_by"]) == (
                feedback["finding_id"], feedback["created_by"]
            ):
                return row
        return None

    def insert_feedback(self, feedback):
        if FakeMySQLStore.fail_next:
            raise ConnectionError("mysql down")
        prior = self._existing(feedback)
        if prior is None:
            FakeMySQLStore.feedback_rows.append(dict(feedback))
            return {"state": "created", "id": feedback["id"]}
        changed = any(
            prior.get(field) != feedback.get(field)
            for field in ("verdict", "reason", "severity", "contract_id")
        )
        # The row keeps the id it was created with: production's upsert
        # updates the verdict columns only, and migration 0012's dedupe is
        # keyed on (finding_id, created_by).
        stored_id = prior["id"]
        prior.update(feedback)
        return {"state": "replaced" if changed else "unchanged", "id": stored_id}

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
    assert resp.json()["state"] == "created"
    assert len(fake_mysql.feedback_rows) == 1


def test_double_click_by_one_reviewer_is_one_verdict(fake_mysql):
    """Go/No-Go #13: acceptance_rate is a ratio of PEOPLE, not of POSTs.

    The same reviewer sending the same accept twice must leave one stored
    row and a 100% rate. Before 0012 the second POST appended a second
    numerator row (the route generated a fresh uuid every call), so a
    reviewer who double-clicked doubled the weight of their verdict.
    """
    fake_mysql.rows["j-1"] = {"id": "j-1", "tenant_id": None}
    client = _client()
    body = {
        "finding_id": "f-1", "contract_id": "AUTH-01",
        "severity": "BLOCKER", "verdict": "accept", "created_by": "u1",
    }
    first = client.post("/api/v1/jobs/j-1/feedback", headers={"X-API-Key": API_KEY}, json=body)
    second = client.post("/api/v1/jobs/j-1/feedback", headers={"X-API-Key": API_KEY}, json=body)
    assert first.json()["state"] == "created"
    assert second.json()["state"] == "unchanged"
    assert second.json()["id"] == first.json()["id"], "the id echoed must be the stored row"
    stats = client.get("/api/v1/jobs/j-1/feedback", headers={"X-API-Key": API_KEY}).json()
    assert stats["stats"] == {
        "job_id": "j-1", "accepted": 1, "rejected": 0,
        "no_feedback_not_counted": True, "acceptance_rate_pct": 100.0,
    }


def test_reviewer_changing_their_mind_replaces_not_adds(fake_mysql):
    fake_mysql.rows["j-1"] = {"id": "j-1", "tenant_id": None}
    client = _client()
    base = {
        "finding_id": "f-1", "contract_id": "AUTH-01",
        "severity": "BLOCKER", "created_by": "u1",
    }
    client.post("/api/v1/jobs/j-1/feedback", headers={"X-API-Key": API_KEY},
                json={**base, "verdict": "accept"})
    flip = client.post("/api/v1/jobs/j-1/feedback", headers={"X-API-Key": API_KEY},
                       json={**base, "verdict": "reject", "reason": "reconsidered"})
    assert flip.json()["state"] == "replaced"
    data = client.get("/api/v1/jobs/j-1/feedback", headers={"X-API-Key": API_KEY}).json()
    assert data["stats"]["accepted"] == 0
    assert data["stats"]["rejected"] == 1
    assert data["stats"]["acceptance_rate_pct"] == 0.0
    assert len(data["rows"]) == 1


def test_stats_rate_and_unknown_job_404(fake_mysql):
    fake_mysql.rows["j-1"] = {"id": "j-1", "tenant_id": None}
    client = _client()
    # Three DIFFERENT findings from one reviewer — the rate is per verdict
    # row, and one reviewer restating one finding counts once (see
    # test_double_click_by_one_reviewer_is_one_verdict).
    for index, verdict in enumerate(("accept", "accept", "reject")):
        resp = client.post("/api/v1/jobs/j-1/feedback", headers={
            "X-API-Key": API_KEY,
        }, json={
            "finding_id": f"f-{index}", "contract_id": "AUTH-01",
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
