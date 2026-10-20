"""Job status progression driven by the pipeline's stages (Phase 3).

The frozen state machine (storage/mysql.py) names five non-terminal
states beyond RUNNING. Until now they had NO production writer — and a
state nobody writes is a state that cannot appear, which makes the
"frozen" machine a decoration rather than a contract. This module is the
writer.

The mapping is by GRAPH STAGE, because the stage is the fact the pipeline
actually produced: "the worktrees are ready" is a fact, and PREPARING is
where the job waits while that is true; "the differential has run, the
court is next" is a fact, and REVIEWING is where the job waits while that
is true.

Two rules, both load-bearing:

1. **A status is written only when the transition is LEGAL from the row's
   current status.** An illegal advance is SKIPPED and counted, never
   forced — a worker must not be able to bend the state machine, and a
   concurrent cancel (which flips the row to CANCELLED) must win over a
   stage that finished a moment later.
2. **A stage that maps to no status leaves the row alone.** The worker
   must not lose the terminal write to a progress write.

The status a stage maps to is the state the job is in AFTER that stage
finished — the graph's ``updates`` stream reports the stage that just
completed, so "preflight finished" means the job has entered the
preparation phase.
"""

from __future__ import annotations

from typing import Any

from observability.metrics import incr

#: The graph stage that just finished → the job status the job is in
#: after it. A stage absent from this table leaves the status alone.
#:
#: The graph's node order (agent/graph.py):
#:   intake → preflight → compile_contracts → prepare_base → prepare_head
#:   → collect_diff → retrieve_repository_context → run_static_checks
#:   → generate_counterexamples → run_differential → run_deep_experiments
#:   → review_court → build_matrix → create_capsule → run_release_checks
#:   → publish_report
STAGE_STATUS: dict[str, str] = {
    # The toolchain is checked and the worktrees are about to be built:
    # the job is PREPARING from here until the head workspace exists.
    "preflight": "PREPARING",
    "compile_contracts": "PREPARING",
    "prepare_base": "PREPARING",
    "prepare_head": "PREPARING",
    # The workspaces exist and the experiments are about to run: the job
    # is RUNNING again (the terminal write happens from here).
    "collect_diff": "RUNNING",
    # The differential has run; the Review Court now decides. The job
    # stays in REVIEWING through the matrix/capsule/report nodes, and the
    # terminal write lands from REVIEWING.
    "run_differential": "REVIEWING",
    "run_deep_experiments": "REVIEWING",
    "review_court": "REVIEWING",
}

#: Counter families.
COUNTER_ADVANCED = "job_stage_advanced_total"
COUNTER_SKIPPED_ILLEGAL = "job_stage_skipped_illegal_transition_total"
COUNTER_SKIPPED_NO_MAPPING = "job_stage_skipped_unmapped_stage_total"


def status_for_stage(stage: str) -> str | None:
    """The job status a finished stage leaves the job in, or None."""
    return STAGE_STATUS.get(stage)


def advance_job_status(
    store: Any,
    job_id: str,
    status: str,
    *,
    worker_id: str | None = None,
) -> bool:
    """Write *status* onto the job IF the transition is legal right now.

    Returns True when the row was written. A refusal is not an error:
    the row may have been cancelled or terminalised by someone else, and
    the worker's own stage must not resurrect it.

    The store is injected (it is a MySQLStore in production, a fake in
    tests) — this module never reaches for a global.
    """
    from storage.mysql import InvalidStateTransition

    try:
        job = store.get_job(job_id)
    except Exception:  # noqa: BLE001 — an unreadable row is "not advanced"
        incr(COUNTER_SKIPPED_ILLEGAL)
        return False
    if not isinstance(job, dict):
        incr(COUNTER_SKIPPED_ILLEGAL)
        return False

    current = str(job.get("status") or "")
    if current == status:
        # Already there — not a failure, and not worth an audit row.
        return False

    try:
        written = store.transition_job_status(
            job_id,
            status,
            from_status=current,
            worker_id=worker_id,
        )
    except InvalidStateTransition:
        # The state machine refused it: the row is somewhere this stage
        # may not go. Skipped, counted, never forced.
        incr(COUNTER_SKIPPED_ILLEGAL)
        return False
    except Exception:  # noqa: BLE001 — the store is unreachable
        incr(COUNTER_SKIPPED_ILLEGAL)
        return False

    if written:
        incr(COUNTER_ADVANCED)
    return bool(written)


def advance_for_stage(
    store: Any,
    job_id: str,
    stage: str,
    *,
    worker_id: str | None = None,
) -> bool:
    """Advance the job to the status the finished *stage* implies.

    Returns True when the row was written. A stage with no mapping is a
    no-op (counted separately) — the worker must not lose its terminal
    write to a progress write it did not ask for.
    """
    status = status_for_stage(stage)
    if status is None:
        incr(COUNTER_SKIPPED_NO_MAPPING)
        return False
    return advance_job_status(store, job_id, status, worker_id=worker_id)


__all__ = [
    "COUNTER_ADVANCED",
    "COUNTER_SKIPPED_ILLEGAL",
    "COUNTER_SKIPPED_NO_MAPPING",
    "STAGE_STATUS",
    "advance_for_stage",
    "advance_job_status",
    "status_for_stage",
]
