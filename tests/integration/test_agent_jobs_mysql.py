"""MySQL integration tests for storage.agent_jobs — gated on MYSQL_URL.

Run with a real MySQL (matches the production backend):

    MYSQL_URL=mysql://user:pass@host:3306/specproof_phase0 \
        python -m pytest tests/integration/test_agent_jobs_mysql.py

Without MYSQL_URL the whole module is skipped at collection — it never
fails and needs no Docker here. Each run cleans the agent_jobs table it
uses (fresh uuid ids + table truncation).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from typing import cast

import pytest

from storage.agent_jobs import (
    InvalidJobTransitionError,
    JobAlreadyExistsError,
    JobStatus,
    MySqlAgentJobStore,
    compute_spec_digest,
)

MYSQL_URL = os.getenv("MYSQL_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        MYSQL_URL is None,
        reason="MYSQL_URL not set — MySQL integration tests skipped",
    ),
]


class FakeClock:
    """Deterministic clock so lease-expiry tests never sleep."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _fresh_id() -> str:
    return f"it-{uuid.uuid4().hex}"


def _clear(store: MySqlAgentJobStore) -> None:
    with store.connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM agent_jobs")


@pytest.fixture
def store() -> Iterator[MySqlAgentJobStore]:
    store = MySqlAgentJobStore(MYSQL_URL)
    store.ensure_schema()
    _clear(store)
    yield store
    _clear(store)


def test_create_get_list_round_trip(store: MySqlAgentJobStore) -> None:
    job_id = _fresh_id()
    job = store.create(job_id, "Add a read-only endpoint.")
    assert job.status == "pending"
    assert job.spec_digest == compute_spec_digest("Add a read-only endpoint.")

    fetched = store.get(job_id)
    assert fetched == job
    assert [entry.id for entry in store.list(status="pending")] == [job_id]


def test_duplicate_create_raises(store: MySqlAgentJobStore) -> None:
    job_id = _fresh_id()
    store.create(job_id, "spec-a")
    with pytest.raises(JobAlreadyExistsError):
        store.create(job_id, "spec-b")


def test_lease_contention_and_expiry_takeover(store: MySqlAgentJobStore) -> None:
    clock = FakeClock()
    timed = MySqlAgentJobStore(MYSQL_URL, now_fn=clock)
    try:
        job_id = _fresh_id()
        timed.create(job_id, "spec-a")
        assert timed.lease(job_id, "worker-a", 60.0) is True
        assert timed.lease(job_id, "worker-b", 60.0) is False

        clock.advance(61.0)  # expired -> takeover
        assert timed.lease(job_id, "worker-b", 60.0) is True
        job = timed.get(job_id)
        assert job is not None
        assert job.lease_owner == "worker-b"
        assert job.lease_expires_at == pytest.approx(clock.now + 60.0)
    finally:
        _clear(timed)


def test_cancel_wins_over_lease(store: MySqlAgentJobStore) -> None:
    job_id = _fresh_id()
    store.create(job_id, "spec-a")
    assert store.lease(job_id, "worker-a", 300.0) is True
    cancelled = store.cancel(job_id, "operator override")
    assert cancelled.status == "cancelled"
    assert cancelled.lease_owner is None
    assert store.renew(job_id, "worker-a", 300.0) is False
    assert store.lease(job_id, "worker-a", 300.0) is False
    with pytest.raises(InvalidJobTransitionError):
        store.update_status(job_id, "running")


def test_status_transitions_and_projection(store: MySqlAgentJobStore) -> None:
    job_id = _fresh_id()
    store.create(job_id, "spec-a")
    store.update_status(job_id, "running")
    running = store.update_status(
        job_id, "succeeded", result_json={"report": {"ok": True}}
    )
    assert running.finished_at is not None
    assert json.loads(running.result_json or "null") == {"report": {"ok": True}}
    with pytest.raises(InvalidJobTransitionError):
        store.update_status(job_id, cast(JobStatus, "failed"))
    with pytest.raises(InvalidJobTransitionError):
        store.set_plan(job_id, {"steps": []})


def test_ensure_schema_idempotent(store: MySqlAgentJobStore) -> None:
    store.ensure_schema()
    store.ensure_schema()
    job_id = _fresh_id()
    store.create(job_id, "spec-a")
    assert store.get(job_id) is not None
