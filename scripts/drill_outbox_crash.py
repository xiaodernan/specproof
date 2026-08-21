"""Drill 4 driver — outbox relay crash window (DRILLS.md §4).

Executes against the live local stack (MySQL + RabbitMQ + Redis + MongoDB).
Sequence:

1. Create one job via the outbox transaction (job + outbox row, QUEUED).
2. Reconstruct the relay's kill window deterministically: publish the row's
   wire envelope to the broker WITHOUT marking the row published — the exact
   state a SIGKILL between broker-confirm and the UPDATE leaves behind.
3. Start the real worker: it consumes the crash-window message and drives
   the job to its terminal state (one terminal transition).
4. Restart the surviving relay logic (OutboxRelay.drain_pending): it re-
   publishes the same event (publish_count = 2) and marks it published.
5. The worker receives the duplicate delivery; its Redis idempotency key
   drops it. Assert: exactly one terminal transition, one summary write,
   identical side-effect counts before/after the duplicate, empty queue,
   idempotency key present.

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

from ops.drills import (  # noqa: E402
    AUTH_FIXTURE_BASE_JAVA,
    AUTH_FIXTURE_CONTROLLER_REL,
    AUTH_FIXTURE_HEAD_JAVA,
    AUTH_FIXTURE_SPEC_TEXT,
    DrillInfraUnavailableError,
    IdempotencyRedis,
    JobAuditStore,
    Publisher,
    SideEffectStore,
    build_deterministic_fixture,
    crash_window_publish,
    outbox_event_id,
    side_effect_counts,
    terminal_transitions,
    wait_for_idempotency_key,
    wait_for_status,
)
from storage.mysql import MySQLStore  # noqa: E402
from storage.outbox_relay import OutboxRelay  # noqa: E402
from storage.rabbitmq import RabbitMQClient  # noqa: E402
from storage.redis import RedisStore  # noqa: E402

VERIFY_QUEUE = "q.p1.verify.job"


def _worker_env() -> dict[str, str]:
    """Deterministic worker environment: no LLM credentials leak in."""
    env = dict(os.environ)
    env.pop("LLM_API_KEY", None)
    env.pop("LLM_BASE_URL", None)
    env.pop("LLM_MODEL", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _queue_message_count(rabbitmq: RabbitMQClient, queue: str) -> int:
    declared = rabbitmq.channel.queue_declare(queue=queue, passive=True)
    return int(declared.method.message_count)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.parse_args()

    store = MySQLStore()
    rabbitmq = RabbitMQClient()
    redis = RedisStore()
    # Versioned, idempotent schema migrations (the same path the
    # integration tests use) — the dev database must be current before a
    # drill touches the outbox/job state machine.
    store.ensure_tables()
    # Scoped hygiene: unpublished outbox rows left by earlier drill runs
    # (this driver's own prefix) would be re-published by the replay step
    # and pollute this run's evidence. Delete only drill-ob-* pending rows.
    with store.connection() as conn:
        conn.cursor().execute(
            "DELETE FROM outbox WHERE aggregate_id LIKE 'drill-ob-%' "
            "AND published_at IS NULL",
        )
    try:
        if not store.is_ready():
            raise DrillInfraUnavailableError("MySQL not reachable")
        if not rabbitmq.is_ready():
            raise DrillInfraUnavailableError("RabbitMQ not reachable")
    except DrillInfraUnavailableError:
        print(json.dumps({"drill": "outbox_crash", "skipped": "infra unavailable"}))
        return 2

    job_id = f"drill-ob-{int(time.time())}"
    fixture_dir = Path(tempfile.mkdtemp(prefix="specproof-drill-ob-fixture-"))
    fixture = build_deterministic_fixture(
        fixture_dir,
        spec_text=AUTH_FIXTURE_SPEC_TEXT,
        java_sources={AUTH_FIXTURE_CONTROLLER_REL: AUTH_FIXTURE_BASE_JAVA},
        head_java_sources={AUTH_FIXTURE_CONTROLLER_REL: AUTH_FIXTURE_HEAD_JAVA},
        padding_files=0,
    )
    fixture_payload = {
        "job_id": job_id,
        "repo_path": fixture["repo_path"],
        "base_ref": fixture["base_ref"],
        "head_ref": fixture["head_ref"],
        "spec_path": fixture["spec_path"],
        "depth": "FAST",
    }
    result: dict[str, Any] = {
        "drill": "outbox_crash_window",
        "job_id": job_id,
    }

    # 1. Job + outbox row in one transaction.
    store.create_job_with_outbox({
        "id": job_id,
        "repo_path": fixture_payload["repo_path"],
        "base_ref": fixture_payload["base_ref"],
        "head_ref": fixture_payload["head_ref"],
        "spec_path": fixture_payload["spec_path"],
        "depth": "FAST",
    })
    rows = store.fetch_pending_outbox_rows(50)
    row = next((r for r in rows if r["aggregate_id"] == job_id), None)
    if row is None:
        print(json.dumps({**result, "failed": "outbox row not found"}))
        return 1
    event_id = outbox_event_id(row)
    result["outbox_row_id"] = row["id"]
    result["event_id"] = event_id

    # 2. Crash-window state: published to the broker, NOT marked published.
    relay = OutboxRelay(mysql=store, rabbitmq=rabbitmq)
    wire = crash_window_publish(
        cast(Publisher, rabbitmq),
        cast(Callable[[Mapping[str, Any]], Mapping[str, Any]], relay._flatten_envelope),
        row,
    )
    result["wire_keys"] = sorted(wire.keys())
    pending_after_publish = any(
        r["id"] == row["id"] for r in store.fetch_pending_outbox_rows(50)
    )
    result["row_still_pending_after_publish"] = pending_after_publish

    # 3. Real worker consumes the crash-window message.
    scratch = Path(tempfile.mkdtemp(prefix="specproof-drill-ob-"))
    worker_out = scratch / "worker.log"
    worker_log_handle = open(worker_out, "w", encoding="utf-8")  # noqa: SIM115 — owned by the child process
    worker_proc = subprocess.Popen(
        [sys.executable, "-m", "agent.worker"],
        cwd=str(scratch),
        env=_worker_env(),
        stdout=worker_log_handle,
        stderr=subprocess.STDOUT,
    )
    result["worker_pid"] = worker_proc.pid
    try:
        terminal = wait_for_status(
            store, job_id, ["VERIFIED", "BLOCKED", "FAILED", "ERROR", "STALE"],
            timeout=600.0,
        )
        result["terminal_status"] = terminal["status"] if terminal else None
        if terminal is None:
            print(json.dumps({**result, "failed": "worker never reached terminal"}))
            return 1
        idem_before = wait_for_idempotency_key(
            cast(IdempotencyRedis, redis.client), event_id, timeout=30.0,
        )
        result["idempotency_key_after_first_delivery"] = idem_before

        side_effect_store = cast(SideEffectStore, store)
        counts_before = side_effect_counts(side_effect_store, job_id)
        result["side_effects_after_first_delivery"] = counts_before

        # 4. The surviving relay re-publishes the same row and marks it.
        published_now = relay.drain_pending()
        result["relay_replay_published_rows"] = published_now
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT publish_count, published_at FROM outbox WHERE id = %s",
                (row["id"],),
            )
            outbox_row = cur.fetchone()
        result["outbox_publish_count"] = int((outbox_row or {}).get("publish_count") or 0)
        result["outbox_published_at_set"] = bool(
            (outbox_row or {}).get("published_at")
        )

        # 5. Duplicate delivery is dropped: counts unchanged, queue drained.
        time.sleep(5.0)
        counts_after = side_effect_counts(side_effect_store, job_id)
        result["side_effects_after_duplicate_delivery"] = counts_after
        result["queue_messages_remaining"] = _queue_message_count(
            rabbitmq, VERIFY_QUEUE,
        )
        result["terminal_transitions"] = len(
            terminal_transitions(cast(JobAuditStore, store), job_id)
        )

        passed = bool(
            counts_before == counts_after
            and counts_before["terminal_transitions"] == 1
            and counts_before["summary_writes"] == 1
            and result["outbox_publish_count"] == 1
            and result["outbox_published_at_set"]
            and idem_before
            and result["queue_messages_remaining"] == 0
        )
        result["passed"] = passed
        result["verdict"] = (
            "PASS — crash-window replay deduplicated, job executed exactly once"
            if passed else "FAIL"
        )
    finally:
        worker_proc.terminate()
        try:
            worker_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker_proc.kill()
        worker_log_handle.close()
    result["worker_log_tail"] = worker_out.read_text(encoding="utf-8")[-1200:]

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
