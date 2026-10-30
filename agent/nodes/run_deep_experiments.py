"""run_deep_experiments node — DEEP verification tier (P3 + P4 wired).

FAST covers static checks + differential. DEEP additionally runs:
  1. Mutation campaign over the PR's changed files in the HEAD workspace —
     the generated counterexample test runs against each mutant; surviving
     mutants are reported as TEST WEAKNESSES (never as findings).
  2. Full-stack state delta — MySQL/Redis/RabbitMQ snapshots before and
     after the HEAD test run, compared against the BASE run's delta, to
     attribute infrastructure-state changes to the PR.

Honesty: infra capture failures are recorded per subsystem (incomplete);
the node never fabricates deltas. Results land in state["deep_results"]
and a deep-report.json is written next to the HTML report.

Cache integrity (backlog #7 / #136): every Maven run here consumes the
seeded cache volume, so the sandbox's own ``cache_note`` is carried into
``deep_results["cache_integrity"]`` instead of being dropped at this
boundary — an unverified cache must be readable in the artifact a reviewer
opens, not only inside the runner.

Command shape (#531): the test command itself is owned by the repository's
ExecutionAdapter. This node used to spell its own ``mvn -o test -q ...``
argv — a second copy of the shape #530 taught the differential to read.
Under ``-q`` a passing surefire run prints no "Tests run:" summary, so a
selector that matched nothing looked exactly like a green run; DEEP kept
that flag while recording only exit codes. The run now returns the
executed test counts alongside the exit evidence, and they reach the
artifact (a subsequent unit makes the stability/mutation readers consume
them instead of reading exit codes alone).

Counters (#198): ``run_deep_experiments_runs_total`` counts every
invocation and ``run_deep_experiments_outcomes_<word>_total`` records how
the attempt ended — ``not_requested`` (depth != DEEP: the healthy FAST
default), ``inputs_missing`` (DEEP WAS requested but there is no head
workspace or no generated test — the tier is silently empty and the word
is the alertable record, since nothing downstream can tell it from
not_requested) or ``completed`` (mutation campaign + state delta stability
ran and the deep report was written). An empty deep_results looks
identical for the first two; the note is prose, not countable.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.job_control import run_with_cancel_checks
from agent.state import Phase0State
from observability.metrics import incr

#: The closed set of ways a DEEP-tier attempt can end (#198). Mirrored by
#: the parity family's regex and the behavior tests — a new word must move
#: all three together.
RUN_DEEP_OUTCOMES = frozenset({
    "completed",      # full campaign ran; deep report written
    "inputs_missing", # DEEP requested but nothing to run it on — tier empty
    "not_requested",  # depth != DEEP — the healthy FAST default
})


def run_deep_experiments_node(state: Phase0State) -> dict[str, Any]:
    incr("run_deep_experiments_runs_total")
    if state.get("depth", "FAST") != "DEEP":
        incr("run_deep_experiments_outcomes_not_requested_total")
        return {"deep_results": {}, "deep_note": "DEEP tier not requested"}

    head_workspace = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    generated_tests_path = state.get("generated_tests_path", "")
    job_id = state.get("job_id")
    if not head_workspace or not generated_tests_path:
        incr("run_deep_experiments_outcomes_inputs_missing_total")
        return {
            "deep_results": {},
            "deep_note": "DEEP skipped: no head workspace or generated test",
        }

    app = str(Path(head_workspace) / app_dir) if app_dir else head_workspace
    results: dict[str, Any] = {}

    # ── 1) Mutation campaign (P4) ────────────────────────────────
    # Import from the reader module itself, not from `run_static_checks`:
    # that module imports the reader under the alias `_read_java_files` for
    # its own use, and importing a name into a module does not re-export it
    # (mypy's no-implicit-reexport). #494 moved the reader to _java_files and
    # left this call site pointing at the alias, which kept CI's `mypy .`
    # step red on master until #497.
    from agent.nodes._java_files import read_main_java_files
    from experiments.mutation import run_mutation_campaign

    sources = read_main_java_files(app)
    mutation_reports: list[dict[str, Any]] = []
    for rel_path, content in sources.items():
        if "test" in rel_path or not rel_path.endswith(".java"):
            continue
        report = run_mutation_campaign(
            rel_path,
            content,
            _make_test_runner(app, rel_path, generated_tests_path, job_id),
            max_mutants=10,
        )
        mutation_reports.append(report.to_dict())
    results["mutation"] = mutation_reports

    # ── 2) Full-stack state delta (P3) ───────────────────────────
    from experiments.state_snapshot import capture_full_stack, diff_states
    from storage.mysql import MySQLStore
    from storage.rabbitmq import RabbitMQClient
    from storage.redis import RedisStore

    mysql = MySQLStore()
    redis = RedisStore()
    rabbitmq = RabbitMQClient()
    before = capture_full_stack(
        mysql, redis, rabbitmq,
        mysql_tables=["verification_jobs", "findings"],
        rabbit_queues=["q.p1.verify.job"],
    )
    head_run = run_with_cancel_checks(
        job_id, "deep_head_run", _run_test_via_sandbox, app, generated_tests_path,
    )
    after = capture_full_stack(
        mysql, redis, rabbitmq,
        mysql_tables=["verification_jobs", "findings"],
        rabbit_queues=["q.p1.verify.job"],
    )
    results["state_delta"] = {
        "head_test_exit": head_run["exit_code"],
        "head_test_error": head_run["error"],
        "head_test_counts": head_run.get("test_counts") or {},
        "diff": diff_states(before, after),
    }

    # ── 3) Verdict stability (P4, §14.1) ────────────────────────────
    # The FAST differential records ONE observation per experiment. DEEP
    # re-runs the generated test on HEAD a bounded number of times and
    # classifies the verdict sequence: stable / flaky / contaminated.
    # Environmental contamination = the H2 state at the start of a repeat
    # differs from the first run's start state (leftover state polluting
    # the re-run). A single run is never called stable.
    from agent.verdict_stability import summarize

    repeats = _env_int("SPECPROOF_DEEP_REPEATS", 2)
    repeat_runs: list[dict[str, Any]] = []
    # Full run views (cache_note included); repeat_runs is projected down to
    # what verdict_stability.summarize consumes (exit/error plus the executed
    # count), so the cache disclosure cannot ride it.
    run_views: list[dict[str, Any]] = [head_run]
    contaminated = False
    baseline_snapshot: dict[str, Any] | None = None
    for index in range(repeats):
        from agent.nodes.run_differential import _capture_db_snapshot

        start_snapshot = _capture_db_snapshot(app)
        if index == 0:
            baseline_snapshot = start_snapshot
        elif baseline_snapshot is not None and (
            start_snapshot.get("rows") != baseline_snapshot.get("rows")
        ):
            contaminated = True
        repeat_run = run_with_cancel_checks(
            job_id, "deep_stability_run",
            _run_test_via_sandbox, app, generated_tests_path,
        )
        repeat_runs.append({
            "exit_code": repeat_run["exit_code"],
            "error": repeat_run["error"],
            # What this repeat actually executed. verdict_stability.summarize
            # publishes the run records as-is, so the artifact shows whether
            # an "exit_0" repeat ran tests or matched nothing (the shape a
            # reader needs before trusting a stability verdict).
            "test_counts": repeat_run.get("test_counts") or {},
        })
        run_views.append(repeat_run)
    results["verdict_stability"] = summarize(repeat_runs, contaminated)

    # What the sandbox said about the cache these runs consumed. Derived from
    # the full run views (head run + stability repeats); the mutation runner
    # is contracted to (exit_code, error) by run_mutation_campaign, so it
    # cannot carry a note.
    cache_integrity = _cache_integrity_disclosure(run_views)
    if cache_integrity:
        results["cache_integrity"] = cache_integrity

    # ── Persist the deep report next to the HTML report ──────────
    out_dir = Path(state.get("output_dir", "reports"))
    out_dir.mkdir(parents=True, exist_ok=True)
    report_name, naming = _deep_report_name(job_id)
    # The artifact carries its own attribution: a reader holding only the file
    # can tell which job produced it and under which name it was written.
    results["job_id"] = job_id or ""
    results["deep_report_file"] = report_name
    results["deep_report_naming"] = naming
    (out_dir / report_name).write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    incr("run_deep_experiments_outcomes_completed_total")
    return {
        "deep_results": results,
        "deep_note": (
            "DEEP experiments completed: mutation campaigns="
            + str(len(mutation_reports))
            + ", state delta captured"
        ),
    }


def _make_test_runner(
    app: str, rel_path: str, generated_tests_path: str,
    job_id: str | None = None,
) -> Callable[[str], tuple[int, str]]:
    """Runner that swaps a mutated source into the workspace and runs the
    generated test via the sandbox. Returns (exit_code, error).

    §14 任务 8: each mutant's Maven run carries before+after cancellation
    checkpoints; the finally-block still restores the original source even
    when a checkpoint raises (workspace cleanup is not a business result).
    """

    target = Path(app) / "src" / "main" / "java" / rel_path

    def runner(mutated_content: str) -> tuple[int, str]:
        original = target.read_text(encoding="utf-8")
        try:
            target.write_text(mutated_content, encoding="utf-8")
            run = run_with_cancel_checks(
                job_id, "deep_mutation_run",
                _run_test_via_sandbox, app, generated_tests_path,
            )
            return run["exit_code"], run["error"]
        finally:
            target.write_text(original, encoding="utf-8")

    return runner


def _env_int(name: str, default: int) -> int:
    """Bounded positive integer from env; falls back to default honestly."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, min(value, 10))


def _run_test_via_sandbox(app: str, generated_tests_path: str) -> dict[str, Any]:
    """Run the generated test once on HEAD through the ExecutionAdapter.

    One owner for the command shape (#531): offline ``-o``, batch ``-B``,
    ``-Dtest=`` injection and the local fallback all come from
    JavaMavenAdapter.prepare(). Spelling them here a second time is how
    this call site kept ``-q`` after #530 replaced it in the differential —
    and under ``-q`` a passing run prints no "Tests run:" summary, so the
    counts below read zero for a green run.
    """
    from experiments.adapters import (
        AdapterNotImplemented,
        ExecutionRequest,
        RepositorySnapshot,
        parse_surefire_summary,
        registry,
    )

    test_class = Path(generated_tests_path).name
    if test_class.endswith(".java"):
        test_class = test_class[:-5]
    try:
        adapter = registry.get(RepositorySnapshot(path=app))
    except AdapterNotImplemented as exc:
        # The differential's _run_generated_test takes the same branch: an
        # unclaimed repository is a recorded "could not run", not a crash.
        return {
            "exit_code": -1,
            "error": str(exc),
            "mode": "",
            "cache_note": "",
            "test_counts": {},
        }
    prepared = adapter.prepare(
        ExecutionRequest(
            workspace=app, goal="run_test", test_class=test_class, timeout=900,
        )
    )
    result = adapter.run(prepared)
    return {
        "exit_code": result.exit_code,
        "error": result.error,
        "mode": result.mode,
        "cache_note": result.cache_note,
        "test_counts": parse_surefire_summary(
            result.stdout_tail + result.stderr_tail
        ),
    }


def _deep_report_name(job_id: str | None) -> tuple[str, str]:
    """(filename, reason) for this job's DEEP artifact.

    The reports directory is SHARED (``state["output_dir"]`` defaults to
    "reports" for every job), so one fixed filename means the second
    concurrent DEEP run silently replaces the first job's mutation / state
    delta / cache evidence — and the surviving artifact no longer says which
    job it describes. Job ids are scoped by their first 8 characters, the
    naming convention the certificate artifacts already use; an id that is
    not id-shaped (ad-hoc CLI runs) keeps the plain historical name rather
    than letting an arbitrary string become part of a path.
    """
    if job_id and re.fullmatch(r"[0-9a-fA-F-]{8,64}", job_id):
        return f"deep-report-{job_id[:8]}.json", "job-scoped"
    return "deep-report.json", "unscoped"


def _cache_integrity_disclosure(runs: list[dict[str, Any]]) -> str:
    """Collapse the DEEP runs' cache-integrity notes into one statement.

    Every distinct non-empty note is kept (they are provenance statements,
    not safety levels, so nothing may be averaged away): if one run reported
    a verified cache and another an unverified one, the reader sees both.
    Empty return means "nothing was disclosed" — the caller omits the key
    rather than writing "", so an absent disclosure can never be misread as
    a clean one.
    """
    seen: list[str] = []
    for run in runs:
        note = str(run.get("cache_note", "")).strip()
        if note and note not in seen:
            seen.append(note)
    return "; ".join(seen)
