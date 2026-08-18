"""Unit tests for storage.agent_jobs — SQLite backend (no Docker, no network).

Covers the Agent-Plan task-3 contract: projection, cancellation, and lease
semantics behind one AgentJobStore protocol. Lease-expiry tests use an
injected fake clock — they never sleep. A parity class re-runs the core
contract against the in-memory backend to prove the protocol, not the
driver, defines the semantics.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from storage.agent_jobs import (
    AcceptAttachError,
    AgentJobStore,
    InMemoryAgentJobStore,
    InvalidJobTransitionError,
    JobAlreadyExistsError,
    JobNotFoundError,
    JobStatus,
    SqliteAgentJobStore,
    compute_spec_digest,
)

SPEC_TEXT = "Add a read-only endpoint GET /api/items to the service."
ANOTHER_SPEC = "Fix the login inversion bug in auth.py."


class FakeClock:
    """Deterministic clock: lease-expiry tests never sleep."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sqlite_store(tmp_path: Path, clock: FakeClock) -> Iterator[SqliteAgentJobStore]:
    store = SqliteAgentJobStore(tmp_path / "agent_jobs.db", now_fn=clock)
    yield store
    store.close()


@pytest.fixture(params=["sqlite", "memory"])
def any_store(
    tmp_path: Path, clock: FakeClock, request: pytest.FixtureRequest
) -> Iterator[AgentJobStore]:
    if request.param == "sqlite":
        store: AgentJobStore = SqliteAgentJobStore(
            tmp_path / "parity.db", now_fn=clock
        )
    else:
        store = InMemoryAgentJobStore(now_fn=clock)
    yield store
    store.close()


class TestCreateAndGet:
    def test_create_persists_projection_fields(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        job = sqlite_store.create("job-1", SPEC_TEXT)
        assert job.id == "job-1"
        assert job.status == "pending"
        assert job.spec_text == SPEC_TEXT
        assert job.created_at == clock.now
        assert job.updated_at == clock.now
        assert job.plan_json is None
        assert job.current_step is None
        assert job.progress_json is None
        assert job.lease_owner is None
        assert job.lease_expires_at is None
        assert job.started_at is None
        assert job.finished_at is None
        assert job.result_json is None
        assert job.accept_json is None
        assert job.error is None

        fetched = sqlite_store.get("job-1")
        assert fetched == job

    def test_spec_digest_is_sha256_hex(self, sqlite_store: SqliteAgentJobStore) -> None:
        job = sqlite_store.create("job-1", SPEC_TEXT)
        expected = hashlib.sha256(SPEC_TEXT.encode("utf-8")).hexdigest()
        assert job.spec_digest == expected
        assert len(job.spec_digest) == 64

    def test_spec_digest_matches_known_vector(self) -> None:
        # sha256("abc") — canonical test vector.
        assert (
            compute_spec_digest("abc")
            == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_spec_digest_stable_and_distinct(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        first = sqlite_store.create("job-a", SPEC_TEXT)
        second = sqlite_store.create("job-b", SPEC_TEXT)
        third = sqlite_store.create("job-c", ANOTHER_SPEC)
        assert first.spec_digest == second.spec_digest
        assert first.spec_digest != third.spec_digest

    def test_create_duplicate_id_raises(self, sqlite_store: SqliteAgentJobStore) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        with pytest.raises(JobAlreadyExistsError):
            sqlite_store.create("job-1", ANOTHER_SPEC)
        original = sqlite_store.get("job-1")
        assert original is not None
        assert original.spec_text == SPEC_TEXT

    def test_get_unknown_job_returns_none(self, sqlite_store: SqliteAgentJobStore) -> None:
        assert sqlite_store.get("nope") is None

    def test_list_empty_store(self, sqlite_store: SqliteAgentJobStore) -> None:
        assert sqlite_store.list() == []

    def test_list_orders_by_created_at(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-a", SPEC_TEXT)
        clock.advance(1.0)
        sqlite_store.create("job-b", SPEC_TEXT)
        clock.advance(1.0)
        sqlite_store.create("job-c", SPEC_TEXT)
        assert [job.id for job in sqlite_store.list()] == ["job-a", "job-b", "job-c"]

    def test_list_filters_by_status(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-a", SPEC_TEXT)
        clock.advance(1.0)
        sqlite_store.create("job-b", SPEC_TEXT)
        clock.advance(1.0)
        sqlite_store.create("job-c", SPEC_TEXT)
        sqlite_store.cancel("job-b", "superseded")
        assert [job.id for job in sqlite_store.list(status="pending")] == [
            "job-a",
            "job-c",
        ]
        assert [job.id for job in sqlite_store.list(status="cancelled")] == ["job-b"]

    def test_list_limit_and_offset(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        for index in range(5):
            sqlite_store.create(f"job-{index}", SPEC_TEXT)
            clock.advance(1.0)
        assert [job.id for job in sqlite_store.list(limit=2)] == ["job-0", "job-1"]
        assert [job.id for job in sqlite_store.list(limit=2, offset=3)] == [
            "job-3",
            "job-4",
        ]

    def test_list_rejects_bad_limit_and_offset(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        with pytest.raises(ValueError):
            sqlite_store.list(limit=0)
        with pytest.raises(ValueError):
            sqlite_store.list(offset=-1)

    def test_reopened_file_sees_previous_jobs(self, tmp_path: Path) -> None:
        path = tmp_path / "reopen.db"
        clock_one = FakeClock()
        first = SqliteAgentJobStore(path, now_fn=clock_one)
        first.create("job-1", SPEC_TEXT)
        first.lease("job-1", "worker-a", 300.0)
        first.set_plan("job-1", {"steps": ["s1", "s2"]})
        first.close()

        clock_two = FakeClock(start=clock_one.now + 10.0)
        second = SqliteAgentJobStore(path, now_fn=clock_two)
        try:
            restored = second.get("job-1")
            assert restored is not None
            assert restored.status == "running"
            assert restored.lease_owner == "worker-a"
            assert restored.plan_json == json.dumps({"steps": ["s1", "s2"]})
        finally:
            second.close()


class TestLease:
    def test_lease_grants_and_marks_running(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        assert sqlite_store.lease("job-1", "worker-a", 30.0) is True
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.status == "running"
        assert job.lease_owner == "worker-a"
        assert job.lease_expires_at == pytest.approx(clock.now + 30.0)
        assert job.started_at == pytest.approx(clock.now)

    def test_lease_takeover_keeps_original_started_at(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        started = clock.now
        sqlite_store.lease("job-1", "worker-a", 10.0)
        clock.advance(11.0)
        assert sqlite_store.lease("job-1", "worker-b", 10.0) is True
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.started_at == pytest.approx(started)

    def test_lease_second_owner_denied(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        assert sqlite_store.lease("job-1", "worker-a", 60.0) is True
        clock.advance(5.0)
        assert sqlite_store.lease("job-1", "worker-b", 60.0) is False
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.lease_owner == "worker-a"
        assert job.lease_expires_at == pytest.approx(clock.now + 55.0)

    def test_lease_same_owner_can_relock_before_expiry(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 60.0)
        clock.advance(10.0)
        assert sqlite_store.lease("job-1", "worker-a", 60.0) is True
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.lease_owner == "worker-a"
        assert job.lease_expires_at == pytest.approx(clock.now + 60.0)

    def test_lease_expired_takeover_by_new_owner(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 10.0)
        clock.advance(11.0)
        assert sqlite_store.lease("job-1", "worker-b", 20.0) is True
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.lease_owner == "worker-b"
        assert job.lease_expires_at == pytest.approx(clock.now + 20.0)

    def test_lease_expired_at_exact_boundary_allows_takeover(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 10.0)
        clock.advance(10.0)  # lease_expires_at == now counts as expired
        assert sqlite_store.lease("job-1", "worker-b", 20.0) is True

    def test_lease_denied_on_terminal_jobs(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-done", SPEC_TEXT)
        sqlite_store.update_status("job-done", "succeeded")
        assert sqlite_store.lease("job-done", "worker-a", 60.0) is False

        sqlite_store.create("job-cancelled", SPEC_TEXT)
        sqlite_store.cancel("job-cancelled", "operator")
        assert sqlite_store.lease("job-cancelled", "worker-a", 60.0) is False

    def test_lease_unknown_job_raises(self, sqlite_store: SqliteAgentJobStore) -> None:
        with pytest.raises(JobNotFoundError):
            sqlite_store.lease("nope", "worker-a", 60.0)

    def test_lease_rejects_nonpositive_ttl(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        with pytest.raises(ValueError):
            sqlite_store.lease("job-1", "worker-a", 0.0)
        with pytest.raises(ValueError):
            sqlite_store.lease("job-1", "worker-a", -5.0)


class TestRenewRelease:
    def test_renew_extends_expiry_for_holder(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 30.0)
        clock.advance(10.0)
        assert sqlite_store.renew("job-1", "worker-a", 60.0) is True
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.lease_expires_at == pytest.approx(clock.now + 60.0)

    def test_renew_denied_for_non_holder(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 30.0)
        clock.advance(10.0)
        assert sqlite_store.renew("job-1", "worker-b", 60.0) is False
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.lease_expires_at == pytest.approx(clock.now + 20.0)

    def test_renew_denied_after_cancel(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 300.0)
        sqlite_store.cancel("job-1", "operator")
        assert sqlite_store.renew("job-1", "worker-a", 300.0) is False

    def test_release_clears_lease_for_holder(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 30.0)
        assert sqlite_store.release("job-1", "worker-a") is True
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.lease_owner is None
        assert job.lease_expires_at is None
        assert job.status == "running"  # release does not change status

    def test_release_denied_for_non_holder(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 30.0)
        assert sqlite_store.release("job-1", "worker-b") is False
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.lease_owner == "worker-a"

    def test_lease_after_release_succeeds_for_new_owner(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 30.0)
        sqlite_store.release("job-1", "worker-a")
        assert sqlite_store.lease("job-1", "worker-b", 30.0) is True


class TestCancel:
    def test_cancel_wins_over_live_lease(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        assert sqlite_store.lease("job-1", "worker-a", 300.0) is True
        clock.advance(1.0)
        cancelled = sqlite_store.cancel("job-1", "operator aborted the run")
        assert cancelled.status == "cancelled"
        assert cancelled.error == "operator aborted the run"
        assert cancelled.lease_owner is None
        assert cancelled.lease_expires_at is None
        assert cancelled.finished_at == pytest.approx(clock.now)

    def test_cancel_blocks_later_mutations(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 300.0)
        sqlite_store.cancel("job-1", "operator")
        clock.advance(9999.0)  # even long after the lease would have expired
        assert sqlite_store.lease("job-1", "worker-b", 60.0) is False
        assert sqlite_store.renew("job-1", "worker-a", 60.0) is False
        with pytest.raises(InvalidJobTransitionError):
            sqlite_store.update_status("job-1", "running")
        with pytest.raises(InvalidJobTransitionError):
            sqlite_store.set_progress("job-1", "s1", {"pct": 10})
        with pytest.raises(InvalidJobTransitionError):
            sqlite_store.set_plan("job-1", {"steps": ["s1"]})

    def test_cancel_idempotent(self, sqlite_store: SqliteAgentJobStore) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        first = sqlite_store.cancel("job-1", "first reason")
        second = sqlite_store.cancel("job-1", "second reason")
        assert first.finished_at == second.finished_at
        assert second.status == "cancelled"
        assert second.error == "second reason"

    def test_cancel_unknown_job_raises(self, sqlite_store: SqliteAgentJobStore) -> None:
        with pytest.raises(JobNotFoundError):
            sqlite_store.cancel("nope", "reason")

    def test_cancel_overrides_succeeded(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.update_status("job-1", "succeeded")
        job = sqlite_store.cancel("job-1", "audit override")
        assert job.status == "cancelled"
        assert job.error == "audit override"


class TestUpdateStatus:
    def test_pending_to_running_sets_started_at(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        clock.advance(1.0)
        job = sqlite_store.update_status("job-1", "running")
        assert job.status == "running"
        assert job.started_at == pytest.approx(clock.now)

    def test_running_to_succeeded_finishes_and_releases_lease(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.lease("job-1", "worker-a", 300.0)
        clock.advance(2.0)
        job = sqlite_store.update_status(
            "job-1", "succeeded", result_json={"report": "ok"}
        )
        assert job.status == "succeeded"
        assert job.finished_at == pytest.approx(clock.now)
        assert job.lease_owner is None
        assert job.lease_expires_at is None
        assert json.loads(job.result_json or "null") == {"report": "ok"}

    def test_pending_to_failed_direct_with_error_and_result(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        clock.advance(3.0)
        job = sqlite_store.update_status(
            "job-1", "failed", error="step timed out", result_json={"step": "s2"}
        )
        assert job.status == "failed"
        assert job.error == "step timed out"
        assert json.loads(job.result_json or "null") == {"step": "s2"}
        assert job.finished_at == pytest.approx(clock.now)

    def test_terminal_status_rejects_transition(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.update_status("job-1", "failed")
        with pytest.raises(InvalidJobTransitionError):
            sqlite_store.update_status("job-1", "running")

    def test_same_status_is_idempotent(self, sqlite_store: SqliteAgentJobStore) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.update_status("job-1", "succeeded")
        again = sqlite_store.update_status("job-1", "succeeded")
        assert again.status == "succeeded"

    def test_unknown_status_string_rejected(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        with pytest.raises(ValueError):
            sqlite_store.update_status("job-1", cast(JobStatus, "bogus"))

    def test_update_status_unknown_job_raises(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        with pytest.raises(JobNotFoundError):
            sqlite_store.update_status("nope", "running")


class TestPlanProgress:
    def test_set_plan_round_trips_json(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        plan = {"steps": [{"id": "s1", "kind": "edit"}], "mode": "llm"}
        clock.advance(4.0)
        job = sqlite_store.set_plan("job-1", plan)
        assert json.loads(job.plan_json or "null") == plan
        assert job.updated_at == pytest.approx(clock.now)

    def test_set_plan_overwrites_previous(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.set_plan("job-1", {"v": 1})
        job = sqlite_store.set_plan("job-1", {"v": 2})
        assert json.loads(job.plan_json or "null") == {"v": 2}

    def test_set_progress_round_trips(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        job = sqlite_store.set_progress(
            "job-1", "step-2", {"iterations": 3, "status": "green"}
        )
        assert job.current_step == "step-2"
        assert json.loads(job.progress_json or "null") == {
            "iterations": 3,
            "status": "green",
        }

    def test_set_plan_unknown_job_raises(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        with pytest.raises(JobNotFoundError):
            sqlite_store.set_plan("nope", {"v": 1})

    def test_set_plan_rejected_after_cancel(
        self, sqlite_store: SqliteAgentJobStore
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.cancel("job-1", "operator")
        with pytest.raises(InvalidJobTransitionError):
            sqlite_store.set_plan("job-1", {"v": 1})

    def test_projection_write_bumps_updated_at_only(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        created = sqlite_store.get("job-1")
        assert created is not None
        clock.advance(5.0)
        sqlite_store.set_progress("job-1", "s1", {"pct": 50})
        job = sqlite_store.get("job-1")
        assert job is not None
        assert job.created_at == created.created_at
        assert job.updated_at == pytest.approx(clock.now)


class TestBackendParity:
    """Same contract, both backends — the protocol is the semantics."""

    def test_parity_create_get_and_digest(self, any_store: AgentJobStore) -> None:
        job = any_store.create("job-1", SPEC_TEXT)
        assert any_store.get("job-1") == job
        assert job.spec_digest == compute_spec_digest(SPEC_TEXT)

    def test_parity_lease_contention_and_takeover(
        self, any_store: AgentJobStore, clock: FakeClock
    ) -> None:
        any_store.create("job-1", SPEC_TEXT)
        assert any_store.lease("job-1", "worker-a", 10.0) is True
        assert any_store.lease("job-1", "worker-b", 10.0) is False
        clock.advance(11.0)
        assert any_store.lease("job-1", "worker-b", 10.0) is True
        job = any_store.get("job-1")
        assert job is not None
        assert job.lease_owner == "worker-b"

    def test_parity_cancel_wins_over_lease(self, any_store: AgentJobStore) -> None:
        any_store.create("job-1", SPEC_TEXT)
        any_store.lease("job-1", "worker-a", 300.0)
        cancelled = any_store.cancel("job-1", "operator")
        assert cancelled.status == "cancelled"
        assert any_store.renew("job-1", "worker-a", 300.0) is False
        assert any_store.lease("job-1", "worker-a", 300.0) is False

    def test_parity_status_transitions(self, any_store: AgentJobStore) -> None:
        any_store.create("job-1", SPEC_TEXT)
        any_store.update_status("job-1", "running")
        any_store.update_status("job-1", "failed", error="boom")
        with pytest.raises(InvalidJobTransitionError):
            any_store.update_status("job-1", "running")




class TestAttachAcceptResult:
    """W35.1 post-hoc accept projection — the only write a terminal job accepts.

    Succeeded/failed targets attach (first write wins, repeats are
    idempotent no-ops); pending/running/cancelled targets reject with
    AcceptAttachError so the closed projection stays closed.
    """

    def test_attach_on_succeeded_writes_and_round_trips(
        self, sqlite_store: SqliteAgentJobStore, clock: FakeClock
    ) -> None:
        sqlite_store.create("job-1", SPEC_TEXT)
        sqlite_store.update_status("job-1", "succeeded", result_json={"report": "ok"})
        clock.advance(1.0)
        payload = {
            "accept_verdict": "VERIFIED",
            "certificate_path": "c.json",
            "gates_report": {"overall": "passed"},
        }
        job = sqlite_store.attach_accept_result("job-1", payload)
        assert json.loads(job.accept_json or "null") == payload
        assert json.loads(job.result_json or "null") == {"report": "ok"}  # loop report untouched
        assert job.updated_at == pytest.approx(clock.now)
        assert sqlite_store.get("job-1") == job

    def test_attach_on_failed_terminal_writes(self, any_store: AgentJobStore) -> None:
        any_store.create("job-1", SPEC_TEXT)
        any_store.update_status("job-1", "failed", error="boom")
        job = any_store.attach_accept_result("job-1", {"accept_verdict": "BLOCKED"})
        assert json.loads(job.accept_json or "null") == {"accept_verdict": "BLOCKED"}
        assert job.error == "boom"  # the loop error stays intact

    def test_attach_rejected_for_non_terminal_jobs(
        self, any_store: AgentJobStore
    ) -> None:
        any_store.create("job-1", SPEC_TEXT)
        with pytest.raises(AcceptAttachError):
            any_store.attach_accept_result("job-1", {"accept_verdict": "VERIFIED"})
        any_store.lease("job-1", "worker-a", 60.0)  # now running, still leased
        with pytest.raises(AcceptAttachError):
            any_store.attach_accept_result("job-1", {"accept_verdict": "VERIFIED"})
        job = any_store.get("job-1")
        assert job is not None and job.accept_json is None

    def test_attach_rejected_for_cancelled_jobs(
        self, any_store: AgentJobStore
    ) -> None:
        any_store.create("job-1", SPEC_TEXT)
        any_store.cancel("job-1", "operator")
        with pytest.raises(AcceptAttachError):
            any_store.attach_accept_result("job-1", {"accept_verdict": "VERIFIED"})
        job = any_store.get("job-1")
        assert job is not None and job.accept_json is None
        assert job.error == "operator"  # cancel wins over a late accept

    def test_attach_is_idempotent_and_first_write_wins(
        self, any_store: AgentJobStore, clock: FakeClock
    ) -> None:
        any_store.create("job-1", SPEC_TEXT)
        any_store.update_status("job-1", "succeeded")
        first = any_store.attach_accept_result(
            "job-1", {"accept_verdict": "BLOCKED", "n": 1}
        )
        clock.advance(1.0)
        second = any_store.attach_accept_result(
            "job-1", {"accept_verdict": "VERIFIED", "n": 2}
        )
        # terminal immutability: the first attach is the record
        assert json.loads(first.accept_json or "null") == {
            "accept_verdict": "BLOCKED",
            "n": 1,
        }
        assert second.accept_json == first.accept_json
        assert second.updated_at == pytest.approx(clock.now)

    def test_attach_unknown_job_raises(self, any_store: AgentJobStore) -> None:
        with pytest.raises(JobNotFoundError):
            any_store.attach_accept_result("nope", {"accept_verdict": "VERIFIED"})

    def test_attach_persists_across_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "attach.db"
        first = SqliteAgentJobStore(path)
        first.create("job-1", SPEC_TEXT)
        first.update_status("job-1", "succeeded")
        first.attach_accept_result(
            "job-1", {"accept_verdict": "VERIFIED", "certificate_path": "c.json"}
        )
        first.close()
        second = SqliteAgentJobStore(path)
        try:
            restored = second.get("job-1")
            assert restored is not None
            assert json.loads(restored.accept_json or "null") == {
                "accept_verdict": "VERIFIED",
                "certificate_path": "c.json",
            }
        finally:
            second.close()

    def test_pre_w351_database_gets_accept_column(self, tmp_path: Path) -> None:
        """ensure_schema upgrades an old table (CREATE IF NOT EXISTS won't)."""
        import sqlite3 as driver

        path = tmp_path / "old.db"
        conn = driver.connect(str(path))
        conn.execute(
            "CREATE TABLE agent_jobs ("
            "id VARCHAR(255) PRIMARY KEY, status VARCHAR(16) NOT NULL, "
            "spec_text TEXT NOT NULL, spec_digest CHAR(64) NOT NULL, "
            "plan_json TEXT, current_step VARCHAR(255), progress_json TEXT, "
            "lease_owner VARCHAR(255), lease_expires_at DOUBLE, started_at DOUBLE, "
            "finished_at DOUBLE, result_json TEXT, error TEXT, "
            "created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL)"
        )
        conn.execute(
            "INSERT INTO agent_jobs (id, status, spec_text, spec_digest, created_at, updated_at) "
            "VALUES ('job-1', 'succeeded', 'old spec', '0' * 64, 1.0, 1.0)"
        )
        conn.commit()
        conn.close()
        store = SqliteAgentJobStore(path)
        try:
            job = store.attach_accept_result("job-1", {"accept_verdict": "BLOCKED"})
            assert json.loads(job.accept_json or "null") == {"accept_verdict": "BLOCKED"}
        finally:
            store.close()

class TestSharedSqlConsistency:
    """White-box guards: the shared SQL is fully static (bandit B608), so the
    terminal-status literals inside it must match the canonical status tuple
    — consistency is enforced by test instead of by construction."""

    def test_terminal_status_lists_match_the_canonical_tuple(self) -> None:
        import storage.agent_jobs as module

        statements = [
            module._LEASE_SQL,
            module._RENEW_SQL,
            module._SET_PLAN_SQL,
            module._SET_PROGRESS_SQL,
            module._UPDATE_STATUS_NONTERMINAL_SQL,
            module._UPDATE_STATUS_TERMINAL_SQL,
        ]
        for statement in statements:
            match = re.search(r"NOT IN \(([^)]*)\)", statement)
            assert match is not None, statement
            found = re.findall(r"'([a-z]+)'", match.group(1))
            assert sorted(found) == sorted(module.TERMINAL_JOB_STATUSES)

    def test_select_statements_share_the_same_column_list(self) -> None:
        import storage.agent_jobs as module

        def columns(statement: str) -> str:
            return statement.removeprefix("SELECT ").split(" FROM ")[0]

        assert columns(module._SELECT_BY_ID_SQL) == columns(module._LIST_SQL)
        assert columns(module._LIST_BY_STATUS_SQL) == columns(module._LIST_SQL)

    def test_attach_sql_targets_the_canonical_terminal_pair(self) -> None:
        """W35.1: the attach UPDATE is static; its IN-list must stay in
        sync with the (succeeded, failed) terminal pair it documents."""
        import storage.agent_jobs as module

        match = re.search(r"IN \(([^)]*)\)", module._ATTACH_ACCEPT_SQL)
        assert match is not None, module._ATTACH_ACCEPT_SQL
        found = re.findall(r"'([a-z]+)'", match.group(1))
        assert sorted(found) == ["failed", "succeeded"]

