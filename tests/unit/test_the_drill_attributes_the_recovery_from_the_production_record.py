"""The drill must attribute the recovery from the PRODUCTION RECORD, not from
its own call.

WHY THIS FILE EXISTS. Measured on 2026-11-13, drill 1 reported **FAIL**:
``recovery_path: "unknown"`` with ``claims_delta: 1``. The production record
of the very same run said the opposite:

    05:52:40  worker-31784  job_status_transition        None -> RUNNING
    05:53:11  reclaimer      job_reclaimed_stale_running  RUNNING -> QUEUED
    05:53:17  worker-34784  job_status_transition        None -> RUNNING
    05:53:38  system         job_status_transition        None -> BLOCKED

The recovery was perfect — same verdict, same evidence, exactly one terminal
transition, and exactly one extra claim (the re-claim a reclaim is supposed
to make). The INSTRUMENT was wrong, in two ways:

* it compared the job id against ``sweep.reclaimed`` — a list of ROWS, not
  ids — so ``job_id in [ {...}, ... ]`` was always False and the drill could
  never name the reclaim path at all;
* it read the path from "did MY sweep call return this job", while the
  system has more than one sweeper (the surviving worker's periodic tick,
  the fresh worker's tick, the drill's own trigger). Whoever gets there
  first wins the row, so "my call found nothing" does not mean "no reclaim
  happened" — it means "another sweeper got there first".

The reclaim writes its OWN audit row, so the truth is in the job's history.
These legs pin that the drill reads it from there.

WHAT THIS DOES NOT CLAIM. It does not prove the drill now PASSES — that is
measured by running the drill against the live stack (DRILLS.md §8.4). It
proves the instrument stopped lying about which path ran.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILL = REPO / "scripts" / "drill_worker_kill.py"


def _source() -> str:
    return DRILL.read_text(encoding="utf-8")


def test_the_reclaimed_rows_are_compared_by_id() -> None:
    """A job id compared against a list of ROWS is always False."""
    source = _source()
    assert "kill_job_id in list(sweep.reclaimed" not in source, (
        "the drill compares a job id against the reclaimed ROWS again — that "
        "comparison is always False, so the reclaim path can never be named"
    )
    assert 'str(row.get("id")) == kill_job_id' in source, (
        "the drill must compare the reclaimed rows by their id"
    )


def test_the_path_is_read_from_the_production_record() -> None:
    """The reclaim writes an audit row; the drill must read it."""
    source = _source()
    assert "RECLAIM_STALE_RUNNING_ACTION" in source, (
        "the drill must read the reclaim's own audit row — the production "
        "record of what happened, not the return value of one call"
    )
    assert "count_audit_actions" in source, (
        "the drill must count the reclaim audit rows for the killed job"
    )


def test_the_report_says_who_reclaimed_it() -> None:
    """"Which sweeper won the row" is a fact a reader wants."""
    source = _source()
    assert '"reclaimed_by"' in source, (
        "the drill's report must say whether ITS trigger or another sweeper "
        "reclaimed the row"
    )
    for word in ("drill-trigger", "another-sweeper"):
        assert word in source, f"the report must distinguish {word!r}"
