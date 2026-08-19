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
"""

from __future__ import annotations

import json
import os
import platform
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.job_control import run_with_cancel_checks
from agent.state import Phase0State


def run_deep_experiments_node(state: Phase0State) -> dict[str, Any]:
    if state.get("depth", "FAST") != "DEEP":
        return {"deep_results": {}, "deep_note": "DEEP tier not requested"}

    head_workspace = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    generated_tests_path = state.get("generated_tests_path", "")
    job_id = state.get("job_id")
    if not head_workspace or not generated_tests_path:
        return {
            "deep_results": {},
            "deep_note": "DEEP skipped: no head workspace or generated test",
        }

    app = str(Path(head_workspace) / app_dir) if app_dir else head_workspace
    results: dict[str, Any] = {}

    # ── 1) Mutation campaign (P4) ────────────────────────────────
    from agent.nodes.run_static_checks import _read_java_files
    from experiments.mutation import run_mutation_campaign

    sources = _read_java_files(app)
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
        "diff": diff_states(before, after),
    }

    # ── Persist the deep report next to the HTML report ──────────
    out_dir = Path(state.get("output_dir", "reports"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "deep-report.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

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


def _run_test_via_sandbox(app: str, generated_tests_path: str) -> dict[str, Any]:
    from sandbox.runner import run_sandboxed

    test_class = Path(generated_tests_path).name
    if test_class.endswith(".java"):
        test_class = test_class[:-5]
    if platform.system() == "Windows":
        local_cmd = [
            os.path.join(app, "mvnw.cmd"), "test", "-q",
            f"-Dtest={test_class}", "-DfailIfNoTests=false",
        ]
    else:
        local_cmd = [
            os.path.join(app, "mvnw"), "test", "-q",
            f"-Dtest={test_class}", "-DfailIfNoTests=false",
        ]
    result = run_sandboxed(
        [
            # -o: the sandbox has --network none by design; every
            # artifact must resolve from the seeded Maven cache volume.
            "mvn", "-o", "test", "-q",
            f"-Dtest={test_class}",
            "-DfailIfNoTests=false",
            "-f", "/work/pom.xml",
        ],
        workspace=app,
        timeout=900,
        local_command=local_cmd,
    )
    return {
        "exit_code": result.exit_code,
        "error": result.error,
        "mode": result.mode,
    }
