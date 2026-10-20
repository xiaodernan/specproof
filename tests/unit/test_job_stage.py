"""Job stage → status progression tests (Phase 3 follow-up to #297).

The frozen state machine names five states beyond RUNNING. These tests
pin the WRITER that makes them reachable, and the two rules that keep it
honest:

- a status is written only when the transition is legal from the row's
  current status (a worker must not be able to bend the state machine);
- a stage that maps to no status leaves the row alone (the terminal write
  must never be lost to a progress write).

The crash-reclaimer side is pinned too: a job that crashed while its
status said PREPARING must still be reclaimable, or the finer-grained
states would strand jobs forever.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.job_stage import (
    COUNTER_SKIPPED_ILLEGAL,
    COUNTER_SKIPPED_NO_MAPPING,
    STAGE_STATUS,
    advance_for_stage,
    advance_job_status,
    status_for_stage,
)
from observability.metrics import snapshot
from storage.mysql import IN_FLIGHT_STATUSES, InvalidStateTransition


def _counter(name: str) -> float:
    return snapshot()["counters"].get(name, 0.0)


class FakeStore:
    """A job store double: one row, a strict state machine."""

    def __init__(self, status: str = "RUNNING") -> None:
        self.status = status
        self.transitions: list[tuple[str, str]] = []

    def get_job(self, job_id: str) -> dict[str, Any]:
        return {"id": job_id, "status": self.status}

    def transition_job_status(
        self, job_id: str, to_status: str, *, from_status: str | None = None,
        worker_id: str | None = None, error_msg: str | None = None,
        **_: Any,
    ) -> bool:
        from storage.mysql import _VALID_TRANSITIONS

        current = from_status or self.status
        if to_status not in _VALID_TRANSITIONS.get(current, set()):
            raise InvalidStateTransition(f"{current} -> {to_status}")
        self.transitions.append((current, to_status))
        self.status = to_status
        return True


# ── the mapping ────────────────────────────────────────────────────────────


class TestStageMapping:
    def test_preparation_stages_map_to_preparing(self) -> None:
        for stage in ("preflight", "compile_contracts", "prepare_base", "prepare_head"):
            assert status_for_stage(stage) == "PREPARING", stage

    def test_the_worktrees_are_ready_so_the_run_is_running_again(self) -> None:
        assert status_for_stage("collect_diff") == "RUNNING"

    def test_the_court_stages_map_to_reviewing(self) -> None:
        for stage in ("run_differential", "run_deep_experiments", "review_court"):
            assert status_for_stage(stage) == "REVIEWING", stage

    def test_an_unmapped_stage_leaves_the_status_alone(self) -> None:
        for stage in ("intake", "build_matrix", "create_capsule", "publish_report", ""):
            assert status_for_stage(stage) is None, stage

    def test_every_mapped_stage_is_a_legal_target(self) -> None:
        """A mapping to a status nothing can hold would be a dead write."""
        from storage.mysql import _VALID_TRANSITIONS

        for stage, status in STAGE_STATUS.items():
            assert status in _VALID_TRANSITIONS, f"{stage} -> {status}"


# ── the writer ─────────────────────────────────────────────────────────────


class TestAdvance:
    def test_a_legal_transition_is_written(self) -> None:
        store = FakeStore("RUNNING")
        assert advance_job_status(store, "job-1", "PREPARING") is True
        assert store.status == "PREPARING"
        assert store.transitions == [("RUNNING", "PREPARING")]

    def test_an_illegal_transition_is_skipped_not_forced(self) -> None:
        """A worker must not be able to bend the state machine."""
        store = FakeStore("VERIFIED")
        before = _counter(COUNTER_SKIPPED_ILLEGAL)
        assert advance_job_status(store, "job-1", "PREPARING") is False
        assert store.status == "VERIFIED"
        assert store.transitions == []
        assert _counter(COUNTER_SKIPPED_ILLEGAL) == before + 1

    def test_a_cancelled_job_is_not_resurrected(self) -> None:
        """A cancel that landed a moment ago wins over a finished stage."""
        store = FakeStore("CANCELLED")
        assert advance_job_status(store, "job-1", "REVIEWING") is False
        assert store.status == "CANCELLED"

    def test_the_same_status_is_not_rewritten(self) -> None:
        store = FakeStore("PREPARING")
        assert advance_job_status(store, "job-1", "PREPARING") is False
        assert store.transitions == []

    def test_an_unreadable_row_is_not_a_crash(self) -> None:
        class Broken:
            def get_job(self, job_id: str) -> dict[str, Any]:
                raise RuntimeError("mysql down")

        before = _counter(COUNTER_SKIPPED_ILLEGAL)
        assert advance_job_status(Broken(), "job-1", "PREPARING") is False
        assert _counter(COUNTER_SKIPPED_ILLEGAL) == before + 1

    def test_a_missing_row_is_not_a_crash(self) -> None:
        class Empty:
            def get_job(self, job_id: str) -> dict[str, Any]:
                return {}

        assert advance_job_status(Empty(), "job-1", "PREPARING") is False

    def test_a_store_failure_is_not_a_crash(self) -> None:
        class Failing:
            def get_job(self, job_id: str) -> dict[str, Any]:
                return {"id": job_id, "status": "RUNNING"}

            def transition_job_status(self, *args: Any, **kwargs: Any) -> bool:
                raise RuntimeError("connection lost")

        before = _counter(COUNTER_SKIPPED_ILLEGAL)
        assert advance_job_status(Failing(), "job-1", "PREPARING") is False
        assert _counter(COUNTER_SKIPPED_ILLEGAL) == before + 1


class TestAdvanceForStage:
    def test_a_mapped_stage_advances(self) -> None:
        store = FakeStore("RUNNING")
        assert advance_for_stage(store, "job-1", "preflight") is True
        assert store.status == "PREPARING"

    def test_an_unmapped_stage_does_nothing(self) -> None:
        """The terminal write must never be lost to a progress write."""
        store = FakeStore("RUNNING")
        before = _counter(COUNTER_SKIPPED_NO_MAPPING)
        assert advance_for_stage(store, "job-1", "publish_report") is False
        assert store.transitions == []
        assert store.status == "RUNNING"
        assert _counter(COUNTER_SKIPPED_NO_MAPPING) == before + 1

    def test_the_full_progression_is_legal_end_to_end(self) -> None:
        """Walking the real stage order never needs an illegal transition."""
        store = FakeStore("RUNNING")
        for stage in (
            "preflight", "compile_contracts", "prepare_base", "prepare_head",
            "collect_diff", "run_differential", "run_deep_experiments",
            "review_court",
        ):
            advance_for_stage(store, "job-1", stage)
        assert store.status == "REVIEWING"
        # …and the terminal write lands from there.
        assert store.transition_job_status(
            "job-1", "VERIFIED", from_status="REVIEWING"
        ) is True


# ── the reclaim side ───────────────────────────────────────────────────────


class TestInFlightStatuses:
    def test_every_in_flight_status_can_be_reclaimed(self) -> None:
        """A job that crashed in PREPARING must not be stranded.

        The reclaimer takes a stale row back to QUEUED. If the in-flight
        set did not include the finer-grained states, a crash in
        PREPARING or REVIEWING would leave the job stuck forever — the
        price of a prettier status vocabulary.
        """
        for status in ("RUNNING", "PREPARING", "CONTRACT_REVIEW", "REVIEWING"):
            assert status in IN_FLIGHT_STATUSES, status

    def test_a_terminal_status_is_never_in_flight(self) -> None:
        for status in ("VERIFIED", "BLOCKED", "NEEDS_REVIEW", "CANCELLED", "STALE"):
            assert status not in IN_FLIGHT_STATUSES, status

    def test_every_in_flight_status_can_return_to_queued(self) -> None:
        """The reclaim's own transition must be legal from each of them."""
        from storage.mysql import _VALID_TRANSITIONS

        for status in IN_FLIGHT_STATUSES:
            assert "QUEUED" in _VALID_TRANSITIONS[status], status


@pytest.mark.parametrize("status", ["PREPARING", "REVIEWING", "CONTRACT_REVIEW"])
def test_the_finer_states_are_reachable_from_running(status: str) -> None:
    from storage.mysql import _VALID_TRANSITIONS

    assert status in _VALID_TRANSITIONS["RUNNING"]


class TestEveryVerdictIsReachable:
    """A verdict the policy can produce must be writable from wherever
    the worker happens to be.

    The worker writes the terminal status from the status its last
    stage left behind. A job whose graph failed before the court phase
    is still RUNNING when the verdict lands — so if the policy can say
    NEEDS_REVIEW but the state machine cannot accept it from RUNNING,
    that job's terminal write raises InvalidStateTransition and the job
    never gets its verdict at all.
    """

    def test_every_verdict_is_writable_from_the_statuses_a_job_ends_in(
        self,
    ) -> None:
        from evidence.verdict import VERDICT_VOCABULARY
        from storage.mysql import _VALID_TRANSITIONS

        # A job that reached the end of the pipeline is RUNNING or
        # REVIEWING when its verdict lands — the stage progression moves
        # it to REVIEWING before the court rules. From either of those,
        # EVERY word the policy can produce must be writable.
        for from_status in ("RUNNING", "REVIEWING"):
            for verdict in VERDICT_VOCABULARY:
                assert verdict in _VALID_TRANSITIONS[from_status], (
                    f"{from_status} -> {verdict} is not a legal transition, but "
                    f"the policy can produce {verdict}"
                )

    def test_an_early_abort_is_writable_from_the_preparation_states(self) -> None:
        """A graph that dies before collect_diff leaves the job PREPARING.

        Its terminal write is FAILED, and that transition has to be legal
        or the job never gets a verdict at all — it would sit in
        PREPARING forever, which is exactly the stuck shape the expiry
        reaper was written for.
        """
        from storage.mysql import _VALID_TRANSITIONS

        for from_status in ("PREPARING", "CONTRACT_REVIEW"):
            assert "FAILED" in _VALID_TRANSITIONS[from_status], from_status

    def test_the_job_status_channel_declares_the_same_word(self) -> None:
        """The channel registry and the policy must agree on the words."""
        from evidence.verdict import VERDICT_VOCABULARY
        from evidence.verdict_channels import CHANNELS

        declared = set(CHANNELS["job_summary"].scale)
        assert declared == VERDICT_VOCABULARY, (
            f"the policy produces {sorted(VERDICT_VOCABULARY)} but the "
            f"job_summary channel declares {sorted(declared)}"
        )
