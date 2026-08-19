"""Drill 1 driver — worker killed mid-job, checkpoint resume, no duplicate
side effects (DRILLS.md §1).

Runs against the live local stack (MySQL + RabbitMQ + Redis + MongoDB +
Elasticsearch + MinIO). Sequence:

1. Build a deterministic fixture repo (auth regression, no pom.xml → the
   differential node degrades honestly; static checks find the regression).
2. KILL job: submit via the outbox transaction, let the real relay publish
   and the real worker consume. Kill the worker (taskkill /F /T) once >=
   KILL_AFTER_CHECKPOINTS checkpoints exist while the job is still RUNNING.
3. Wait for the crashed worker's Redis lease to expire, then resume the job
   in-process under the same thread_id (LangGraph skips completed nodes) and
   drive the single terminal transition.
4. CONTROL job: the same fixture run uninterrupted.
5. Assert: both jobs reach the same verdict with identical side-effect
   counts, and the killed job has exactly one terminal transition.

Exit codes: 0 = PASS, 1 = FAIL, 2 = infrastructure unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.mongo_saver import MongoDBSaver  # noqa: E402
from agent.worker import (  # noqa: E402
    Worker,
    _state_summary,
    _terminal_status_from_state,
)
from ops.drills import (  # noqa: E402
    AUTH_FIXTURE_BASE_JAVA,
    AUTH_FIXTURE_CONTROLLER_REL,
    AUTH_FIXTURE_HEAD_JAVA,
    AUTH_FIXTURE_SPEC_TEXT,
    CheckpointCollection,
    DrillInfraUnavailableError,
    JobAuditStore,
    SideEffectStore,
    build_deterministic_fixture,
    resume_job,
    side_effect_counts,
    wait_for_checkpoint_count,
    wait_for_lease_available,
    wait_for_status,
)
from storage.mysql import MySQLStore  # noqa: E402
from storage.outbox_relay import OutboxRelay  # noqa: E402
from storage.rabbitmq import RabbitMQClient  # noqa: E402
from storage.redis import RedisStore  # noqa: E402

KILL_AFTER_CHECKPOINTS = 6


def _checkpoint_collection() -> Any:
    """The Mongo collection the graph checkpointer writes (thread_id == job_id)."""
    return MongoDBSaver().collection


def _fixture(root: Path, padding: int) -> dict[str, str]:
    return build_deterministic_fixture(
        root,
        spec_text=AUTH_FIXTURE_SPEC_TEXT,
        java_sources={AUTH_FIXTURE_CONTROLLER_REL: AUTH_FIXTURE_BASE_JAVA},
        head_java_sources={AUTH_FIXTURE_CONTROLLER_REL: AUTH_FIXTURE_HEAD_JAVA},
        padding_files=padding,
    )


def _payload(job_id: str, fixture: Mapping[str, str]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "repo_path": fixture["repo_path"],
        "base_ref": fixture["base_ref"],
        "head_ref": fixture["head_ref"],
        "spec_path": fixture["spec_path"],
        "depth": "FAST",
    }


def _submit_job(store: MySQLStore, payload: dict[str, Any]) -> None:
    store.create_job_with_outbox({
        "id": payload["job_id"],
        "repo_path": payload["repo_path"],
        "base_ref": payload["base_ref"],
        "head_ref": payload["head_ref"],
        "spec_path": payload["spec_path"],
        "depth": payload["depth"],
    })


def _worker_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("LLM_API_KEY", None)
    env.pop("LLM_BASE_URL", None)
    env.pop("LLM_MODEL", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _kill_process_tree(pid: int) -> None:
    """Kill a Windows process tree (worker) the way an operator would."""
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _resume(
    store: MySQLStore,
    redis: RedisStore,
    job_id: str,
    payload: dict[str, Any],
) -> str:
    """In-process resume: lease → graph (same thread_id) → terminal transition."""
    worker_id = f"drill-resume-{os.getpid()}"
    worker = Worker(worker_id=worker_id)
    return resume_job(
        cast(Any, worker),  # Worker.execute_job provides the resume surface
        cast(Any, redis),   # RedisStore provides acquire/release/get_owner
        cast(JobAuditStore, store),
        job_id,
        payload,
        worker_id,
        verdict_fn=cast(
            Callable[[Mapping[str, Any]], str], _terminal_status_from_state,
        ),
        summary_fn=cast(
            Callable[[Mapping[str, Any], str], Mapping[str, Any]], _state_summary,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument(
        "--padding", type=int, default=40,
        help="pad Java files on both refs to widen the kill window",
    )
    args = parser.parse_args()

    store = MySQLStore()
    rabbitmq = RabbitMQClient()
    redis = RedisStore()
    # Versioned, idempotent schema migrations (the same path the
    # integration tests use) — the dev database must be current before a
    # drill touches the outbox/job state machine.
    store.ensure_tables()
    checkpoints = cast(CheckpointCollection, _checkpoint_collection())
    result: dict[str, Any] = {"drill": "worker_kill_recovery"}
    try:
        if not store.is_ready():
            raise DrillInfraUnavailableError("MySQL not reachable")
        if not rabbitmq.is_ready():
            raise DrillInfraUnavailableError("RabbitMQ not reachable")
        checkpoints.count_documents({})  # raises when Mongo is unreachable
    except DrillInfraUnavailableError:
        print(json.dumps({"drill": "worker_kill_recovery", "skipped": "infra unavailable"}))
        return 2
    except Exception as exc:  # noqa: BLE001 — recorded honestly below
        result["infra_probe_error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 2

    # ── shared deterministic fixture (both jobs use the same repo) ──
    fixture_root = Path(tempfile.mkdtemp(prefix="specproof-drill-wk-fixture-"))
    fixture = _fixture(fixture_root, padding=args.padding)
    result["fixture"] = {
        "repo_path": fixture["repo_path"],
        "base_ref": fixture["base_ref"],
        "head_ref": fixture["head_ref"],
        "padding_files": args.padding,
    }

    scratch = Path(tempfile.mkdtemp(prefix="specproof-drill-wk-cwd-"))
    relay = OutboxRelay(mysql=store, rabbitmq=rabbitmq)
    side_effect_store = cast(SideEffectStore, store)

    # ── KILL job ──
    kill_job_id = f"drill-wk-{int(time.time())}"
    kill_payload = _payload(kill_job_id, fixture)
    _submit_job(store, kill_payload)
    relay.drain_pending()  # real relay publish (one cycle)

    worker_out = scratch / "worker.log"
    worker_log_handle = open(worker_out, "w", encoding="utf-8")  # noqa: SIM115 — owned by the child process
    worker_proc = subprocess.Popen(
        [sys.executable, "-m", "agent.worker"],
        cwd=str(scratch),
        env=_worker_env(),
        stdout=worker_log_handle,
        stderr=subprocess.STDOUT,
    )
    kill_log: dict[str, Any] = {"job_id": kill_job_id, "worker_pid": worker_proc.pid}
    result["kill_job"] = kill_log
    checkpoint_count = 0
    kill_counts: dict[str, int] = {}
    kill_checkpoints_after = 0
    try:
        running = wait_for_status(store, kill_job_id, ["RUNNING"], timeout=300.0)
        if running is None:
            kill_log["error"] = "worker never reached RUNNING"
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 1
        checkpoint_count = wait_for_checkpoint_count(
            checkpoints, kill_job_id, KILL_AFTER_CHECKPOINTS, timeout=600.0,
        )
        kill_log["checkpoints_before_kill"] = checkpoint_count
        if checkpoint_count < KILL_AFTER_CHECKPOINTS:
            kill_log["error"] = "job finished before the kill window"
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 1
        # Kill the worker mid-graph (checkpoint machinery already persisted).
        _kill_process_tree(worker_proc.pid)
        worker_proc.wait(timeout=30)
        kill_log["worker_killed"] = True
        kill_log["killed_at_checkpoints"] = checkpoint_count
        kill_log["kill_log_tail"] = worker_out.read_text(encoding="utf-8")[-800:]

        stuck = wait_for_status(store, kill_job_id, ["RUNNING"], timeout=30.0)
        kill_log["stuck_running_after_kill"] = stuck is not None
        kill_log["lease_owner_after_kill"] = redis.get_lease_owner(kill_job_id)
        if stuck is None:
            kill_log["error"] = "job not RUNNING after kill (moved to terminal?)"
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 1

        # ── resume after lease expiry (the crashed worker's 30s TTL) ──
        lease_waited = wait_for_lease_available(
            cast(Any, redis), kill_job_id, timeout=90.0,
        )
        kill_log["lease_available_after_ttl"] = lease_waited
        resume_started = time.monotonic()
        verdict = _resume(store, redis, kill_job_id, kill_payload)
        kill_log["resume_seconds"] = round(time.monotonic() - resume_started, 2)
        kill_log["verdict"] = verdict
        terminal = wait_for_status(
            store, kill_job_id,
            ["VERIFIED", "BLOCKED", "FAILED", "ERROR", "STALE"], timeout=120.0,
        )
        kill_log["terminal_status"] = terminal["status"] if terminal else None
        kill_counts = side_effect_counts(side_effect_store, kill_job_id)
        kill_checkpoints_after = checkpoints.count_documents(
            {"thread_id": kill_job_id},
        )
        kill_log["side_effects"] = kill_counts
        kill_log["checkpoints_after_resume"] = kill_checkpoints_after
    finally:
        worker_proc.terminate()
        try:
            worker_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker_proc.kill()
        worker_log_handle.close()

    # ── CONTROL job: same fixture, no kill ──
    control_job_id = f"drill-wk-ctl-{int(time.time())}"
    control_payload = _payload(control_job_id, fixture)
    _submit_job(store, control_payload)
    relay.drain_pending()
    control_row = wait_for_status(store, control_job_id, ["QUEUED"], timeout=60.0)
    if control_row is not None:
        store.transition_job_status(control_job_id, "RUNNING")
    control_verdict = _resume(store, redis, control_job_id, control_payload)
    control_counts = side_effect_counts(side_effect_store, control_job_id)
    result["control_job"] = {
        "job_id": control_job_id,
        "verdict": control_verdict,
        "side_effects": control_counts,
    }

    # ── assertions ──
    same_verdict = kill_log["verdict"] == result["control_job"]["verdict"]
    same_counts = kill_counts == control_counts
    one_terminal = kill_counts.get("terminal_transitions") == 1
    resumed_forward = kill_checkpoints_after >= checkpoint_count
    result["assertions"] = {
        "same_verdict_as_control": same_verdict,
        "identical_side_effect_counts": same_counts,
        "exactly_one_terminal_transition": one_terminal,
        "checkpoints_advanced_after_resume": resumed_forward,
    }
    passed = bool(same_verdict and same_counts and one_terminal and resumed_forward)
    result["passed"] = passed
    result["verdict"] = (
        "PASS — killed worker resumed via checkpoints; one terminal state; "
        "no duplicate side effects" if passed else "FAIL"
    )

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
