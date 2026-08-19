"""Run the SpecProof verify worker with the RabbitMQ consumption loop pumped (W43.1).

The stock "python -m agent.worker" entry has two latent regressions on the
current HEAD (observed live in the one-command start, reported to the
owning lanes):

1. main() registers the consumer on q.p1.verify.job but never pumps the
   blocking connection — the process exits right after "starting
   consumption" and queued JobCreated messages stay messages_ready with
   zero unacked;
2. Worker.start() passes RedisStore.set_idempotent as the idempotency
   check, whose boolean is inverted relative to the consumer contract
   ("True = duplicate"); storage.rabbitmq.make_idempotency_check is the
   matching adapter.

This launcher keeps the exact Worker wiring but supplies the correct
adapter and calls RabbitMQClient.start_consuming(), so a job submitted via
POST /jobs actually runs QUEUED -> RUNNING -> terminal. It touches no
existing source and is the entry point scripts/start_local.ps1 uses.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.worker import Worker  # noqa: E402
from observability.logging import configure_logging  # noqa: E402
from observability.tracing import init_tracing  # noqa: E402
from storage.rabbitmq import (  # noqa: E402
    RabbitMQClient,
    make_idempotency_check,
)

_QUEUE_VERIFY_JOB = "q.p1.verify.job"


def _run() -> int:
    configure_logging()
    init_tracing(service_name="specproof-worker")

    # Process-local /metrics (same port contract as agent.worker:main).
    try:
        from observability.metrics_http import serve_metrics_in_thread

        serve_metrics_in_thread(port=int(os.getenv("WORKER_METRICS_PORT", "9100")))
    except Exception as exc:  # noqa: BLE001 — metrics are optional telemetry
        print(f"[run_worker] metrics server unavailable: {exc}", file=sys.stderr)

    worker = Worker()

    def _shutdown(signum: int, frame: Any) -> None:
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Mirrors Worker.start() with the corrected idempotency adapter, then
    # pumps deliveries (the step the stock main() is missing).
    worker._running = True
    worker.rabbitmq.ensure_topology()
    worker.rabbitmq.consume_with_policy(
        queue=RabbitMQClient.QUEUE_VERIFY_JOB,
        callback=worker._handle_job,
        policy=None,
        idempotency_fn=make_idempotency_check(worker.redis),
    )
    worker.rabbitmq.start_consuming()
    worker.stop()
    return 1  # connection lost: exit non-zero so logs/starts show it


def main() -> int:
    if _QUEUE_VERIFY_JOB != RabbitMQClient.QUEUE_VERIFY_JOB:
        print("[run_worker] queue name drift — refusing to start", file=sys.stderr)
        return 2
    return _run()


if __name__ == "__main__":
    sys.exit(main())
