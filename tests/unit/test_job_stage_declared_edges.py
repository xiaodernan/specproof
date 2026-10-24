"""#448 — the job-stage writer's corners the existing gate does not reach.

``agent/job_stage.py`` is the only production writer for the frozen state
machine's finer-grained statuses. ``test_job_stage.py`` already pins the
mapping, the legal/illegal/cancelled/unreadable paths and the end-to-end
progression.

What it does not reach:

* a job row that is **not a dict** (a list / ``None``) — the module has a
  dedicated skip-and-count branch for it;
* a store whose ``transition_job_status`` **returns falsy without
  raising** — the caller must hear "not written" and must not count it as
  advanced;
* the ``COUNTER_ADVANCED`` increment itself (a successful write is counted);
* the "already at that status" path counting **nothing** at all — it is
  neither an advance nor a skip;
* ``worker_id`` actually being **forwarded** to the store, both directly
  and through ``advance_for_stage``;
* ``advance_for_stage`` reporting an illegal stage transition the same way
  ``advance_job_status`` does.

The module is unchanged by this file: these are behaviour pins.
"""
from __future__ import annotations

from typing import Any

from agent.job_stage import (
    COUNTER_ADVANCED,
    COUNTER_SKIPPED_ILLEGAL,
    COUNTER_SKIPPED_NO_MAPPING,
    advance_for_stage,
    advance_job_status,
)
from observability.metrics import snapshot
from storage.mysql import InvalidStateTransition


def _counter(name: str) -> float:
    return snapshot()["counters"].get(name, 0.0)


class FakeStore:
    """A strict state-machine double, like the one in test_job_stage."""

    def __init__(self, status: str = "RUNNING") -> None:
        self.status = status
        self.transitions: list[tuple[str, str]] = []

    def get_job(self, job_id: str) -> dict[str, Any]:
        return {"id": job_id, "status": self.status}

    def transition_job_status(
        self,
        job_id: str,
        to_status: str,
        *,
        from_status: str | None = None,
        worker_id: str | None = None,
        **_: Any,
    ) -> bool:
        from storage.mysql import _VALID_TRANSITIONS

        current = from_status or self.status
        if to_status not in _VALID_TRANSITIONS.get(current, set()):
            raise InvalidStateTransition(f"{current} -> {to_status}")
        self.transitions.append((current, to_status))
        self.status = to_status
        return True


# ── A row that is not a dict ────────────────────────────────────────────


def test_a_non_dict_row_is_skipped_and_counted() -> None:
    class WeirdRow:
        def get_job(self, job_id: str) -> Any:
            return ["not", "a", "dict"]

    before = _counter(COUNTER_SKIPPED_ILLEGAL)
    assert advance_job_status(WeirdRow(), "job-1", "PREPARING") is False
    assert _counter(COUNTER_SKIPPED_ILLEGAL) == before + 1


def test_a_none_row_is_skipped_and_counted() -> None:
    class NoneRow:
        def get_job(self, job_id: str) -> Any:
            return None

    before = _counter(COUNTER_SKIPPED_ILLEGAL)
    assert advance_job_status(NoneRow(), "job-1", "PREPARING") is False
    assert _counter(COUNTER_SKIPPED_ILLEGAL) == before + 1


# ── A store that writes nothing without raising ─────────────────────────


def test_a_store_returning_falsy_is_reported_not_written_and_not_counted() -> None:
    class NoWrite(FakeStore):
        def transition_job_status(self, *args: Any, **kwargs: Any) -> bool:
            return False  # no raise, no write

    before_advanced = _counter(COUNTER_ADVANCED)
    before_illegal = _counter(COUNTER_SKIPPED_ILLEGAL)
    store = NoWrite("RUNNING")

    assert advance_job_status(store, "job-1", "PREPARING") is False
    # not advanced, and not a skip either — the store simply wrote nothing.
    assert _counter(COUNTER_ADVANCED) == before_advanced
    assert _counter(COUNTER_SKIPPED_ILLEGAL) == before_illegal


# ── The counters themselves ─────────────────────────────────────────────


def test_a_successful_write_counts_as_advanced() -> None:
    before = _counter(COUNTER_ADVANCED)
    store = FakeStore("RUNNING")
    assert advance_job_status(store, "job-1", "PREPARING") is True
    assert _counter(COUNTER_ADVANCED) == before + 1


def test_the_already_there_path_counts_nothing_at_all() -> None:
    before_advanced = _counter(COUNTER_ADVANCED)
    before_illegal = _counter(COUNTER_SKIPPED_ILLEGAL)
    before_unmapped = _counter(COUNTER_SKIPPED_NO_MAPPING)
    store = FakeStore("PREPARING")

    assert advance_job_status(store, "job-1", "PREPARING") is False
    assert store.transitions == []
    assert _counter(COUNTER_ADVANCED) == before_advanced
    assert _counter(COUNTER_SKIPPED_ILLEGAL) == before_illegal
    assert _counter(COUNTER_SKIPPED_NO_MAPPING) == before_unmapped


# ── worker_id forwarding ────────────────────────────────────────────────


def test_worker_id_is_forwarded_to_the_store() -> None:
    seen: dict[str, Any] = {}

    class Recorder(FakeStore):
        def transition_job_status(
            self,
            job_id: str,
            to_status: str,
            *,
            from_status: str | None = None,
            worker_id: str | None = None,
            **kwargs: Any,
        ) -> bool:
            seen.update(
                job_id=job_id, to_status=to_status,
                from_status=from_status, worker_id=worker_id,
            )
            return True

    assert advance_job_status(Recorder("RUNNING"), "job-1", "PREPARING", worker_id="w-7")
    assert seen == {
        "job_id": "job-1",
        "to_status": "PREPARING",
        "from_status": "RUNNING",
        "worker_id": "w-7",
    }


def test_advance_for_stage_forwards_worker_id() -> None:
    seen: dict[str, Any] = {}

    class Recorder(FakeStore):
        def transition_job_status(
            self,
            job_id: str,
            to_status: str,
            *,
            from_status: str | None = None,
            worker_id: str | None = None,
            **kwargs: Any,
        ) -> bool:
            seen.update(to_status=to_status, worker_id=worker_id)
            return True

    assert advance_for_stage(Recorder("RUNNING"), "job-1", "preflight", worker_id="w-9")
    assert seen == {"to_status": "PREPARING", "worker_id": "w-9"}


def test_advance_for_stage_reports_an_illegal_stage_transition() -> None:
    store = FakeStore("VERIFIED")  # no stage may move a VERIFIED job
    before = _counter(COUNTER_SKIPPED_ILLEGAL)
    assert advance_for_stage(store, "job-1", "preflight") is False
    assert store.status == "VERIFIED"
    assert store.transitions == []
    assert _counter(COUNTER_SKIPPED_ILLEGAL) == before + 1
