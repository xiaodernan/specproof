"""The CI workflow's shape is a contract, and this file pins two parts of it.

Both were long-standing queue items that only a workflow change could
close, and both were stuck because nobody could push a workflow file:

1. the **integration leg** must reach the compose services with real
   credentials (the unit harness strips the password variables on
   purpose) — the MySQL-backed gate otherwise never connects to a
   MySQL at all;
2. the **full** golden-case evaluation needs a home: it is a
   multi-hour gate (#373 measured 271-882 s per case locally), so it
   runs on a schedule, never on every push.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    # PyYAML parses the bare `on:` key as the boolean True.
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers() -> dict:
    doc = _workflow()
    return doc[True] if True in doc else doc["on"]


def _jobs() -> dict:
    return _workflow()["jobs"]


def test_the_workflow_has_a_schedule_trigger() -> None:
    """Without a schedule the full evaluation has no home: the per-push
    job runs a 4-case subset, and the whole set is only a historical
    number nobody has re-measured since the case set grew."""
    triggers = _triggers()
    assert "schedule" in triggers, (
        "the workflow has no schedule — the full-case evaluation can "
        "never run on its own"
    )
    crons = [entry.get("cron") for entry in triggers["schedule"]]
    assert crons and all(cron for cron in crons), (
        f"the schedule has no cron: {triggers['schedule']}"
    )


def test_the_full_evaluation_job_evaluates_the_whole_set() -> None:
    jobs = _jobs()
    assert "eval-full-golden-cases" in jobs, (
        "the workflow has no job for the full golden-case evaluation"
    )
    job = jobs["eval-full-golden-cases"]
    body = "\n".join(
        str(step.get("run", "")) for step in job["steps"]
    )
    assert "--cases golden-cases" in body, (
        "the full-evaluation job does not evaluate the whole case set"
    )
    # The floors are the anti-collapse guard: a run that quietly measured
    # four cases must FAIL, not read as "Recall 100%".
    assert "--min-positive-cases" in body
    assert "--min-negative-cases" in body
    assert "--min-recall 100" in body
    assert "--max-false-positives 0" in body


def test_the_full_evaluation_job_does_not_run_on_every_push() -> None:
    """It is a multi-hour gate: on every push it would block every
    merge for hours."""
    job = _jobs()["eval-full-golden-cases"]
    condition = str(job.get("if") or "")
    assert "schedule" in condition or "workflow_dispatch" in condition, (
        "the full-evaluation job would run on every push"
    )


def test_the_full_evaluation_report_is_kept() -> None:
    """A failed multi-hour run must leave something to read."""
    job = _jobs()["eval-full-golden-cases"]
    uploads = [
        step for step in job["steps"]
        if str(step.get("uses") or "").startswith("actions/upload-artifact")
    ]
    assert uploads, "the full evaluation uploads no artifact"
    paths = str(uploads[0].get("with", {}).get("path") or "")
    assert "eval-report" in paths


def test_the_integration_leg_reaches_the_compose_services() -> None:
    """The unit harness strips the password variables on purpose, so the
    integration leg has to bring the credentials itself — otherwise the
    MySQL-backed gate never talks to a MySQL."""
    job = _jobs()["tests-with-infra"]
    env = {str(k): str(v) for k, v in (job.get("env") or {}).items()}
    assert "MYSQL_URL" in env, (
        "the integration leg has no MYSQL_URL — the MySQL-backed tests "
        "would run without a database"
    )
    assert "REDIS_URL" in env, (
        "the integration leg has no REDIS_URL — the Redis-backed tests "
        "would run without a Redis"
    )
