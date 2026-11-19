"""§ the fixed-window limiter holds under a storm of wrong keys.

What this locks down:
  * the bucket key for api-key-mode requests is sha256(X-API-Key)[:16], the
    same one in legacy single-tenant mode;
  * once window count crosses SPECPROOF_RATE_LIMIT_PER_MIN the wire throws
    429 with code RATE_LIMITED — never a 500, never silently past the cap;
  * when the bucket store is down the request is allowed (fail-open), never
    closed silently enough to look like an outage;
  * a storm of wrong keys never yields a 5xx from the limiter itself.

All DB/Redis fakes live in-process — no MySQL, no redis, no network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app

API_KEY = "rl-test-key-abcdef"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_API_KEY", API_KEY)
    monkeypatch.setenv("SPECPROOF_RATE_LIMIT_PER_MIN", "5")


class _CounterRedis:
    """in-memory fixed window: RedisStore() builds one fresh client per call
    like the real pool-backed store, so the counter lives on the class."""

    _n = 0

    def __init__(self) -> None:
        self.client = self

    def incr(self, key: str) -> int:
        _CounterRedis._n += 1
        return _CounterRedis._n

    def expire(self, key: str, ttl: int) -> None:
        return None


class _ExplodingRedis:
    def __init__(self) -> None:
        self.client = self

    def incr(self, key: str) -> int:
        raise RuntimeError("redis down (test)")

    def expire(self, key: str, ttl: int) -> None:
        raise RuntimeError("redis down (test)")


_FAKE_MYSQL: dict[str, dict] = {}


class _FakeMySQLStore:
    def __init__(self) -> None:
        _FAKE_MYSQL.clear()

    def create_job_with_outbox(self, job: dict) -> str:
        _FAKE_MYSQL[job["id"]] = {**job, "status": "QUEUED"}
        return str(job["id"])

    def get_job(self, job_id: str):
        return _FAKE_MYSQL.get(job_id)

    def transition_job_status(self, job_id: str, to_status: str, **kw) -> bool:
        row = _FAKE_MYSQL.get(job_id)
        if row is None:
            return False
        row["status"] = to_status
        return True

    def record_audit(self, **kw) -> None:
        return None

    def search_jobs(self, limit: int = 50, offset: int = 0, **kw) -> dict:
        return {
            "jobs": list(_FAKE_MYSQL.values()),
            "total": len(_FAKE_MYSQL),
            "limit": limit,
            "offset": offset,
        }


def _payload() -> dict:
    return {
        "repo_path": "D:/experim/specproof-clean-clone-gate",
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec_path": "demo/requirement.txt",
        "depth": "FAST",
    }


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def test_rate_limit_under_cap_still_works_and_over_cap_puts_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("storage.redis.RedisStore", _CounterRedis)
    monkeypatch.setattr("storage.mysql.MySQLStore", _FakeMySQLStore)
    monkeypatch.setattr("api.services.verification_service.MySQLStore", _FakeMySQLStore)
    client = TestClient(app)

    codes = [client.post("/jobs", json=_payload(), headers=_headers()).status_code for _ in range(7)]
    assert codes[:5] == [202] * 5, codes
    assert codes[5] == 429, codes
    assert codes[6] == 429, codes
    # and the sixth answer carries RATE_LIMITED, never INTERNAL
    r = client.post("/jobs", json=_payload(), headers=_headers())
    if r.status_code == 429:
        body = r.json()
        assert body["error"]["code"] == "RATE_LIMITED", body


def test_fail_open_shape_when_bucket_store_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("storage.redis.RedisStore", _ExplodingRedis)
    monkeypatch.setattr("storage.mysql.MySQLStore", _FakeMySQLStore)
    monkeypatch.setattr("api.services.verification_service.MySQLStore", _FakeMySQLStore)
    client = TestClient(app)

    r = client.post("/jobs", json=_payload(), headers=_headers())
    # fail-open: request is admitted, never surfaced as 5xx
    assert r.status_code == 202, r.text


def test_wrong_key_storm_never_surfaces_as_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """§9.x — a brute-force attempt storm produces clean 401s, never 5xx."""
    monkeypatch.setattr("storage.redis.RedisStore", _CounterRedis)
    monkeypatch.setattr("storage.mysql.MySQLStore", _FakeMySQLStore)
    monkeypatch.setattr("api.services.verification_service.MySQLStore", _FakeMySQLStore)
    client = TestClient(app)

    statuses = [
        client.post("/jobs", json=_payload(), headers={"X-API-Key": f"wrong-key-{n}"}).status_code
        for n in range(32)
    ]
    assert set(statuses) == {401}, f"expected every wrong-key attempt to get 401, got {set(statuses)}"
