"""Drill 1 driver — worker killed mid-job, production crash-recovery, no
duplicate side effects (DRILLS.md §1).

Runs against the live local stack (MySQL + RabbitMQ + Redis + MongoDB +
Elasticsearch + MinIO). Sequence:

1. Build a deterministic fixture repo (auth regression, no pom.xml — the
   differential node degrades honestly; static checks find the regression).
2. CONTROL job: a job the real worker runs uninterrupted, submitted the
   same way through the outbox transaction; waits for its terminal state.
3. KILL job: the same job submitted through the outbox transaction. The
   worker starts, claims the message and runs the pipeline; while the row
   is RUNNING, the harness kills the worker process tree with
   taskkill /F /T. The worker's Redis lease expires; production recovers
   stale RUNNING rows by CAS-ing them back to QUEUED and re-delivering
   with a FRESH event_id (`reclaim_stale_running_jobs`, the same function
   the periodic tick and `specproof ops recover` call) -- the broker's own
   requeue would be dropped by the worker's Redis idempotency gate by
   design. The drill triggers that production sweep and starts a fresh
   worker, which claims the re-delivered job and resumes from the
   checkpoint (LangGraph skips completed nodes).
4. Assert: both jobs reach the same terminal verdict with identical
   side-effect counts, and the killed job has exactly one terminal
   transition.

Exit codes: 0 = PASS, 1 = FAIL, 2 = infrastructure unavailable.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.mongo_saver import MongoDBSaver  # noqa: E402
from agent.worker import reclaim_stale_running_jobs  # noqa: E402
from ops.drills import (  # noqa: E402
    AUTH_FIXTURE_BASE_JAVA,
    AUTH_FIXTURE_CONTROLLER_REL,
    AUTH_FIXTURE_HEAD_JAVA,
    AUTH_FIXTURE_SPEC_TEXT,
    DrillInfraUnavailableError,
    JobAuditStore,
    SideEffectStore,
    build_deterministic_fixture,
    count_audit_actions,
    side_effect_counts,
    terminal_transitions,
    wait_for_lease_available,
    wait_for_status,
)
from storage.mysql import (  # noqa: E402
    RECLAIM_STALE_RUNNING_ACTION,
    MySQLStore,
)
from storage.outbox_relay import OutboxRelay  # noqa: E402
from storage.rabbitmq import RabbitMQClient  # noqa: E402
from storage.redis import RedisStore  # noqa: E402

#: Terminal statuses the pipeline can settle on (same vocabulary as the
#: state machine in storage/mysql.py).
TERMINAL_STATUSES = (
    "VERIFIED",
    "BLOCKED",
    "NEEDS_REVIEW",
    "FAILED",
    "ERROR",
    "CANCELLED",
    "STALE",
    "EXPIRED",
)


def _worker_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    # A free metrics port: the drill's worker must not fight another worker
    # on this host for :9100. It lost that fight on 2026-11-12 — the bind
    # raised WinError 10048 and the worker DIED AT STARTUP, so the drill's own
    # worker never ran the job it had submitted. Port 0 means "any free
    # port" (the metrics endpoint is the drill's business, nobody else's).
    env["WORKER_METRICS_PORT"] = "0"
    return env


def _kill_process_tree(pid: int) -> None:
    """Kill a Windows process tree (worker) the way an operator would."""
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )


def _start_worker(worker_out: Path) -> subprocess.Popen[str]:
    # Popen keeps its own reference to the file descriptor; the handle is
    # wrapped in a context manager so the drill never leaks an open file.
    handle = open(worker_out, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    env = _worker_env()
    # The drill's own provenance must not leak into the worker beyond what the
    # project provides; the worker should run exactly as in production.
    proc = subprocess.Popen(
        [sys.executable, "-m", "agent.worker"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8", errors="replace",
    )
    return proc


def _worker_log_tail(path: Path) -> str:
    # The worker writes in the console encoding of its own process, so the
    # log is NOT necessarily UTF-8: reading it strictly raised a
    # UnicodeDecodeError INSIDE the drill's report, and the drill lost
    # the very evidence it was trying to show.
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-1200:]
    except OSError as exc:
        return f"<worker log unreadable: {exc}>"


def main() -> int:
    # The console's encoding is not the repository's: on a GBK console a
    # character the worker logged (the replacement character a partial
    # UTF-8 sequence leaves behind) made the drill's OWN report fail to
    # print -- the evidence was lost by the tool that produced it. The
    # report is written as UTF-8 and never dies on an unprintable
    # character.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        with contextlib.suppress(Exception):
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument(
        "--padding", type=int, default=40,
        help="pad Java files on both refs to widen the fixture",
    )
    args = parser.parse_args()

    store = MySQLStore()
    # heartbeat=0: the broker closes an idle connection after two missed
    # heartbeats, and a drill waits MINUTES between publishes by design
    # (the control job alone ran 18 minutes on 2026-11-12). The pump in
    # RabbitMQClient.keepalive() services the connection while a wait is
    # running, but a connection that was idle BEFORE the first pump (or
    # after a broker-side close) cannot be revived -- and the drill lost
    # its kill-leg publish exactly that way (StreamLostError, outbox
    # row 45). A drill client does not need the broker to reap it.
    rabbitmq = RabbitMQClient(heartbeat=0)
    redis = RedisStore()
    # Versioned, idempotent schema migrations (the same path the
    # integration tests use) — the dev database must be current before a
    # drill touches the outbox/job state machine.
    store.ensure_tables()
    result: dict[str, Any] = {"drill": "worker_kill_recovery"}
    # The queue is shared with whatever the operator left behind; the
    # depth is part of the reading (a worker serves the oldest event
    # first, so a backlog is why a leg waits).
    try:
        declared = rabbitmq.channel.queue_declare(
            queue="q.p1.verify.job", passive=True,
        )
        result["queue_depth_at_start"] = int(declared.method.message_count)
    except Exception:  # noqa: BLE001 - a missing queue is a fact too
        result["queue_depth_at_start"] = None
    try:
        if not store.is_ready():
            raise DrillInfraUnavailableError("MySQL not reachable")
        if not rabbitmq.is_ready():
            raise DrillInfraUnavailableError("RabbitMQ not reachable")
        MongoDBSaver().collection.count_documents({})
    except DrillInfraUnavailableError:
        print(json.dumps({"drill": "worker_kill_recovery", "skipped": "infra unavailable"}))
        return 2
    except Exception as exc:  # noqa: BLE001 — recorded honestly below
        result["infra_probe_error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 2

    # ── shared deterministic fixture (both jobs use the same repo) ──
    fixture_root = Path(tempfile.mkdtemp(prefix="specproof-drill-wk-fixture-"))
    fixture = build_deterministic_fixture(
        fixture_root,
        spec_text=AUTH_FIXTURE_SPEC_TEXT,
        java_sources={AUTH_FIXTURE_CONTROLLER_REL: AUTH_FIXTURE_BASE_JAVA},
        head_java_sources={AUTH_FIXTURE_CONTROLLER_REL: AUTH_FIXTURE_HEAD_JAVA},
        padding_files=args.padding,
    )
    result["fixture"] = {
        "repo_path": fixture["repo_path"],
        "base_ref": fixture["base_ref"],
        "head_ref": fixture["head_ref"],
        "padding_files": args.padding,
    }

    scratch = Path(tempfile.mkdtemp(prefix="specproof-drill-wk-cwd-"))
    relay = OutboxRelay(mysql=store, rabbitmq=rabbitmq)
    side_effect_store = cast(SideEffectStore, store)

    def _submit_and_publish(job_id: str) -> None:
        """Insert the job and its outbox event, and publish via the real
        relay so the queue carries the exact same shape as production."""
        store.create_job_with_outbox({
            "id": job_id,
            "repo_path": fixture["repo_path"],
            "base_ref": fixture["base_ref"],
            "head_ref": fixture["head_ref"],
            "spec_path": fixture["spec_path"],
            "depth": "FAST",
        })
        relay.drain_pending()

    # ── CONTROL job: uninterrupted ──
    control_job_id = f"drill-wk-ctl-{int(time.time())}"
    _submit_and_publish(control_job_id)
    control_out = scratch / "control-worker.log"
    control_proc = _start_worker(control_out)
    try:
        control_terminal = wait_for_status(
            # The queue is shared: a worker consumes what is oldest first,
            # so a backlog of earlier events is served before this job is
            # claimed. The wait has to outlast that backlog (the drill
            # prints its own queue depth so a reader can see the wait).
            store, control_job_id, TERMINAL_STATUSES, timeout=3_600.0,
        )
    finally:
        control_proc.terminate()
        try:
            control_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            control_proc.kill()
    result["control_job"] = {
        "job_id": control_job_id,
        "terminal_status": control_terminal["status"] if control_terminal else None,
        "side_effects": side_effect_counts(side_effect_store, control_job_id),
        "worker_log_tail": _worker_log_tail(control_out),
    }
    if control_terminal is None:
        # A timeout is a fact about the tree, so the report has to carry it:
        # where the job stood and for how long it had been running. The LLM
        # path under a rate-limited gateway can take hours (measured 2026-11-12:
        # ~18 minutes for one control job, ~3 hours for another) — the drill
        # does not get to call that a product defect, and it must not hide it
        # behind a one-line message either.
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT status, created_at, updated_at FROM verification_jobs "
                "WHERE id = %s",
                (control_job_id,),
            )
            row = cur.fetchone()
        result["control_job"]["last_known_status"] = (
            str(row["status"]) if row else None
        )
        result["control_job"]["updated_at"] = (
            str(row["updated_at"]) if row else None
        )
        result["error"] = (
            "control job never reached a terminal state within the drill's "
            "window (see last_known_status: the LLM path can take hours under "
            "a rate-limited gateway)"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 1

    # ── KILL job ──
    kill_job_id = f"drill-wk-{int(time.time())}"
    _submit_and_publish(kill_job_id)
    kill_out = scratch / "kill-worker.log"
    kill_proc = _start_worker(kill_out)
    kill_log: dict[str, Any] = {"job_id": kill_job_id, "worker_pid": kill_proc.pid}
    result["kill_job"] = kill_log
    kill_terminal: dict[str, Any] | None = None
    try:
        # The worker must have claimed the job and be mid-flight. The
        # production recovery path this drill exercises only reclaims rows
        # left in RUNNING by a dead heartbeat (reclaim_stale_running_jobs /
        # `specproof ops recover`), so the kill must land inside that
        # window. The row is RUNNING from claim until the first
        # stage-boundary advance (the LLM stages keep it there for minutes).
        running = wait_for_status(
            store, kill_job_id, ["RUNNING"], timeout=900.0,
            keepalive=rabbitmq.keepalive,
        )
        if running is None:
            kill_log["error"] = (
                "job never reached RUNNING (or advanced past it before the "
                "poll saw it) -- the reclaim sweep only recovers RUNNING rows"
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 1
        kill_log["claimed_status"] = running["status"]

        # The kill must land mid-flight: the job may be in ANY non-terminal
        # stage at the moment the worker dies (RUNNING, PREPARING,
        # CONTRACT_REVIEW, REVIEWING) — the assertion that matters is the
        # opposite of completion: the job must NOT have reached a terminal
        # state before the kill landed.
        _kill_process_tree(kill_proc.pid)
        kill_proc.wait(timeout=30)
        kill_log["worker_killed"] = True

        deadline = time.monotonic() + 30.0
        terminal_before: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            with store.connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT status FROM verification_jobs WHERE id = %s",
                    (kill_job_id,),
                )
                row = cur.fetchone()
            if row and row["status"] in TERMINAL_STATUSES:
                terminal_before = dict(row)
                break
            time.sleep(0.25)

        kill_log["terminal_before_resume"] = terminal_before is not None
        kill_log["status_after_kill"] = terminal_before["status"] if terminal_before else None
        kill_log["worker_log_tail_after_kill"] = _worker_log_tail(kill_out)
        if terminal_before is not None:
            kill_log["error"] = (
                "job reached " + str(terminal_before["status"]) + " before the kill landed"
                " — there is no crash to recover from"
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 1

        # The crashed worker's lease must have expired before the sweep can
        # judge the row. The lease TTL is 30 seconds.
        wait_for_lease_available(
            cast(Any, redis), kill_job_id, timeout=120.0,
        )
        # The sweep's CAS also requires updated_at to be older than the
        # lease TTL. The row was written RUNNING at claim; make sure the
        # stamp is stale before sweeping, bounded so an honest miss is
        # reported instead of hung on.
        stale_deadline = time.monotonic() + 120.0
        while time.monotonic() < stale_deadline:
            with store.connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT updated_at FROM verification_jobs WHERE id = %s",
                    (kill_job_id,),
                )
                row = cur.fetchone()
            if row and row["updated_at"] is not None:
                age = time.time() - row["updated_at"].timestamp()
                if age > 35.0:
                    break
            time.sleep(1.0)
        updated_at = row.get("updated_at") if row else None
        kill_log["updated_at_age_before_sweep"] = (
            round(time.time() - updated_at.timestamp(), 1)
            if isinstance(updated_at, datetime.datetime)
            else None
        )

        # Fresh worker consumes the re-delivery. The broker's own requeue
        # would be dropped by the worker's Redis idempotency gate (set before
        # the pipeline runs) — that is why production recovers through the
        # reclaim sweep, which re-delivers with a FRESH event_id.
        resume_out = scratch / "resume-worker.log"
        resume_proc = _start_worker(resume_out)
        try:
            sweep = reclaim_stale_running_jobs()
            kill_log["reclaim_sweep"] = {
                "candidates": sweep.candidates,
                "probed": sweep.probed,
                "lease_probe_error": sweep.lease_probe_error,
                "reclaimed": [r.get("id") for r in sweep.reclaimed],
                "exhausted": [r.get("id") for r in sweep.exhausted],
            }
            kill_terminal = wait_for_status(
                store, kill_job_id, TERMINAL_STATUSES, timeout=3_600.0,
            )
        finally:
            resume_proc.terminate()
            try:
                resume_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                resume_proc.kill()
        kill_log["terminal_status_after_resume"] = (
            kill_terminal["status"] if kill_terminal else None
        )
        kill_log["resume_log_tail"] = _worker_log_tail(resume_out)
        kill_log["terminal_transitions"] = len(
            terminal_transitions(cast(JobAuditStore, store), kill_job_id),
        )
        kill_log["side_effects"] = side_effect_counts(side_effect_store, kill_job_id)
    finally:
        with contextlib.suppress(Exception):
            kill_proc.terminate()

    if kill_terminal is None:
        result["error"] = "killed job never reached a terminal state after resume"
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 1

    # ── assertions ──
    #
    # The crash path leaves ONE footprint of its own: the job is claimed a
    # second time (the killed worker had already claimed it). So "identical
    # side-effect counts" is the WRONG contract — it would fail exactly the
    # behaviour the drill exists to prove. The honest contract is:
    #
    #   * the VERDICT is the same as the uninterrupted control job;
    #   * the EVIDENCE is the same (summary / findings / capsules / errors)
    #     — nothing was written twice;
    #   * there is exactly ONE terminal transition (the job was not judged
    #     twice);
    #   * and the job was claimed exactly ONCE MORE than the control job —
    #     the re-claim the recovery path is supposed to make, and no more
    #     (a second re-claim would mean the sweep looped).
    same_verdict = kill_terminal["status"] == control_terminal["status"]
    kill_counts = kill_log["side_effects"]
    control_counts = result["control_job"]["side_effects"]
    evidence_keys = ("summary_present", "findings", "capsules", "errors")
    same_evidence = all(
        kill_counts.get(key) == control_counts.get(key) for key in evidence_keys
    )
    one_terminal = kill_log.get("terminal_transitions") == 1
    claims = int(kill_counts.get("running_transitions") or 0) - int(
        control_counts.get("running_transitions") or 0
    )
    # WHICH production path finished the job matters, and the report has to
    # say it instead of pretending there is only one:
    #   * "sweep" — the reclaim sweep CAS-ed the stale RUNNING row back to
    #     QUEUED and re-delivered it with a FRESH event_id; the re-claim is
    #     visible as exactly one extra claim;
    #   * "queue-redelivery" — the broker re-delivered the un-acked message
    #     and ANOTHER consumer on the shared queue finished the job (the
    #     drill cannot claim the sweep was exercised then, and the extra
    #     claim is absent because the same worker ran it);
    #   * "unknown" — neither: the job finished some other way.
    # WHICH production path finished the job -- read from the PRODUCTION
    # RECORD, not from this drill's own call.
    #
    # The system has more than one sweeper: the surviving worker's periodic
    # tick, the fresh worker's tick, and the drill's own trigger. They all
    # call the SAME production function, and whichever gets there first wins
    # the row. So "my sweep call returned an empty list" does NOT mean "no
    # sweep happened" -- it means "another sweeper got there first", and a
    # drill that believes otherwise reports the recovery as "unknown" and
    # fails a run that in fact recovered PERFECTLY (measured 2026-11-13:
    # the audit trail showed the reclaim at 05:53:11, the re-claim at
    # 05:53:17, and exactly one terminal transition -- while the drill's own
    # sweep had already found nothing to do).
    #
    # The reclaim writes its OWN audit row (RECLAIM_STALE_RUNNING_ACTION),
    # so the truth is in the row's history: that is what this now reads.
    reclaimed_by_sweep = count_audit_actions(
        cast(JobAuditStore, store), kill_job_id, RECLAIM_STALE_RUNNING_ACTION
    ) > 0
    # The reclaimed list holds ROWS (dicts), not ids -- comparing a job id
    # against it with `in` was always False, so the drill could NEVER
    # attribute the sweep path and reported every sweep recovery as
    # "unknown" (a FAIL) even when the recovery was perfect. That is the
    # instrument lying, not the product.
    swept = reclaimed_by_sweep or any(
        str(row.get("id")) == kill_job_id for row in (sweep.reclaimed or [])
    )
    recovery_path = "sweep" if swept else (
        "queue-redelivery" if claims == 0 else "unknown"
    )
    claim_footprint_ok = (claims == 1) if swept else (claims == 0)
    result["assertions"] = {
        "same_verdict_as_control": same_verdict,
        "identical_evidence": same_evidence,
        "exactly_one_terminal_transition_after_resume": one_terminal,
        "recovery_path": recovery_path,
        "claim_footprint_matches_path": claim_footprint_ok,
        "claims_delta": claims,
        # Who did the reclaim: the drill's own trigger, or another sweeper in
        # the same production fleet (the surviving worker's periodic tick).
        "reclaimed_by": (
            "drill-trigger"
            if any(
                str(row.get("id")) == kill_job_id
                for row in (sweep.reclaimed or [])
            )
            else ("another-sweeper" if reclaimed_by_sweep else "none")
        ),
    }
    result["side_effects_detail"] = {
        "control": control_counts,
        "killed": kill_counts,
    }
    passed = bool(
        same_verdict and same_evidence and one_terminal and claim_footprint_ok
    )
    result["passed"] = passed
    result["verdict"] = (
        f"PASS — killed worker recovered via the production path ({recovery_path}); "
        "same verdict, same evidence, exactly one terminal transition"
        if passed else "FAIL"
    )

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
