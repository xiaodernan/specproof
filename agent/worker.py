"""P1 Worker — RabbitMQ consumer driving the verification pipeline.

Start: python -m agent.worker [--consumer-name worker-1]

Consumes from q.p1.verify.job, manages lifecycle through the MySQL
state machine, and writes progress events to Redis Stream via
graph.stream() for per-node progress reporting.

P1.6 (LangGraph checkpoint recovery) is deferred to P1-B.

Atomic idempotency contract:
  INSERT processed_events → state transition (QUEUED→PREPARING→RUNNING)
  → COMMIT.  All in one MySQL TX.  If the event was already processed
  (dup key), the TX is rolled back and the handler returns — the
  RabbitMQ layer Acks and discards the duplicate.

After the TX commits, the graph executes without holding a DB TX.
The lease guards against duplicate execution during graph processing.
"""

import logging
import signal
import sys
import time
import uuid
from typing import Any

import pymysql

from agent.graph import build_phase0_graph
from agent.state import initial_state
from storage.mysql import JobNotFoundError, MySQLStore
from storage.rabbitmq import (
    PermanentFailureError,
    QueueSpec,
    RabbitMQClient,
    TemporaryFailureError,
)
from storage.redis import RedisStore

logger = logging.getLogger(__name__)

_GRAPH_NODES = [
    "intake", "compile_contracts", "prepare_base", "prepare_head",
    "collect_diff", "run_static_checks", "generate_counterexamples",
    "run_differential", "review_court", "build_matrix",
    "create_capsule", "publish_report",
]


class P1Worker:
    """Consumes JobCreated events, executes the Phase 0 graph, manages lifecycle."""

    QUEUE = QueueSpec(
        name="q.p1.verify.job",
        dlq_name="q.p1.verify.job.dlq",
        retry_name="q.p1.verify.job.retry",
        max_retries=3,
        retry_delays_ms=[1000, 5000, 30000],
    )

    def __init__(
        self,
        consumer_name: str = "worker-1",
        mysql: MySQLStore | None = None,
        redis_store: RedisStore | None = None,
        rabbitmq: RabbitMQClient | None = None,
    ) -> None:
        self.consumer_name = consumer_name
        self.worker_id = str(uuid.uuid4())
        self.mysql = mysql or MySQLStore()
        self.redis = redis_store or RedisStore()
        self.rabbitmq = rabbitmq or RabbitMQClient()
        self._running = False
        self._compiled_graph = build_phase0_graph()

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        self.mysql.ensure_tables()
        self.rabbitmq.ensure_p1_topology()

        self._running = True
        logger.info(
            "P1Worker %s (id=%s) starting, queue=%s",
            self.consumer_name, self.worker_id, self.QUEUE.name,
        )

        self.rabbitmq.consume_with_dlq(
            queue_spec=self.QUEUE,
            callback=self._handle_job_created,
            consumer_name=self.consumer_name,
        )

        try:
            self.rabbitmq.start_consuming()
        except KeyboardInterrupt:
            logger.info("Worker %s shutting down", self.consumer_name)
        finally:
            self._running = False
            self.rabbitmq.close()
            self.redis.close()

    def stop(self) -> None:
        self._running = False

    # ── Message handler ───────────────────────────────────────────

    def _handle_job_created(self, payload: dict[str, Any]) -> None:
        event_id = payload.get("event_id", "unknown")
        job_id = payload.get("job_id", "")
        trace_id = payload.get("trace_id", str(uuid.uuid4()))

        logger.info(
            "Worker %s received event %s for job %s",
            self.consumer_name, event_id, job_id,
        )

        # ── Atomic idempotency claim + state transition in one TX ──
        try:
            with self.mysql.connection() as conn:
                claimed = self.mysql.insert_processed_event_in_tx(
                    conn, self.consumer_name, event_id,
                )
                if not claimed:
                    logger.info(
                        "Event %s already processed by %s, skipping",
                        event_id, self.consumer_name,
                    )
                    return  # TX rolled back on IntegrityError — return, RabbitMQ Acks

                # Transition QUEUED → PREPARING → RUNNING in same TX
                self.mysql.transition_job_status_in_tx(
                    conn, job_id, "PREPARING",
                    worker_id=self.worker_id, trace_id=trace_id,
                )
                self.mysql.transition_job_status_in_tx(
                    conn, job_id, "RUNNING",
                    worker_id=self.worker_id, trace_id=trace_id,
                )
            # TX committed: event claimed + job is RUNNING
        except (JobNotFoundError, pymysql.err.IntegrityError) as e:
            logger.exception("Cannot claim event %s: %s", event_id, e)
            raise PermanentFailureError(str(e)[:200]) from e

        try:
            self._run_job(job_id, payload, trace_id)
        except (TemporaryFailureError, PermanentFailureError):
            raise
        except Exception as e:
            logger.exception("Job %s failed permanently: %s", job_id, e)
            try:
                self.mysql.transition_job_status(
                    job_id, "FAILED",
                    worker_id=self.worker_id,
                    error_msg=str(e)[:4000],
                    error_code="WORKER_FATAL",
                    trace_id=trace_id,
                )
            except Exception:
                logger.exception("Failed to mark job %s as FAILED", job_id)
            self._xadd_event(job_id, "worker_crash", {"error": str(e)[:500]})
            raise PermanentFailureError(str(e)[:200]) from e

    def _run_job(
        self, job_id: str, payload: dict[str, Any], trace_id: str,
    ) -> None:
        # ── QUEUED→PREPARING→RUNNING already done atomically with
        #     the idempotency claim in _handle_job_created ──

        # ── Acquire lease ──
        if not self.redis.acquire_lease(job_id, self.worker_id, ttl=300):
            raise TemporaryFailureError("Cannot acquire lease for job " + job_id)

        self.redis.init_budget(job_id)

        try:
            state = initial_state(
                repo_path=payload.get("repo_path", ""),
                base_ref=payload.get("base_ref", ""),
                head_ref=payload.get("head_ref", ""),
                spec_path=payload.get("spec_path", ""),
            )
            config: dict[str, Any] = {"configurable": {"thread_id": job_id}}

            # ── Execute graph with per-node progress via stream() ──
            node_index: dict[str, int] = {n: i for i, n in enumerate(_GRAPH_NODES)}
            total = len(_GRAPH_NODES)
            final_state: dict[str, Any] = {}

            for event in self._compiled_graph.stream(state, config):  # type: ignore[attr-defined]
                for node_name, node_output in event.items():
                    if not self._running:
                        raise TemporaryFailureError("Worker shutting down")

                    self.redis.renew_lease(job_id, self.worker_id, ttl=300)

                    if self.redis.is_budget_exceeded(job_id):
                        raise PermanentFailureError("Budget exceeded")

                    idx = node_index.get(node_name, -1)
                    self._xadd_event(job_id, "node_complete", {
                        "node": node_name,
                        "percent": round((idx + 1) / total * 100, 1),
                    })
                    final_state = node_output

            # ── Determine final status ──
            findings = final_state.get("confirmed_findings", [])
            has_blocker = any(
                f.get("severity") == "BLOCKER" for f in findings
            ) if isinstance(findings, list) else False

            final_status = "FAILED" if has_blocker else "SUCCEEDED"
            self._transit(job_id, final_status, trace_id,
                         worker_id=self.worker_id, msg="Graph execution completed")

            self._xadd_event(job_id, "job_complete", {
                "status": final_status,
                "findings_count": len(findings) if isinstance(findings, list) else 0,
                "percent": 100.0,
            })

        finally:
            self.redis.release_lease(job_id, self.worker_id)

    # ── Helpers ───────────────────────────────────────────────────

    def _transit(
        self, job_id: str, to_status: str, trace_id: str,
        *, worker_id: str | None = None, msg: str | None = None,
    ) -> int:
        try:
            return self.mysql.transition_job_status(
                job_id, to_status,
                worker_id=worker_id or self.worker_id,
                trace_id=trace_id,
                error_msg=msg,
            )
        except JobNotFoundError:
            raise PermanentFailureError(f"Job {job_id} not found") from None

    def _xadd_event(self, job_id: str, event_type: str, data: dict[str, Any]) -> None:
        try:
            self.redis.xadd_progress(job_id, {
                "event": event_type,
                "worker_id": self.worker_id,
                "timestamp": time.time(),
                **data,
            })
        except Exception:
            logger.warning("Failed to write progress event for job %s", job_id)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    consumer_name = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    worker = P1Worker(consumer_name=consumer_name)

    def _shutdown(signum: int, frame: Any) -> None:
        logger.info("Received signal %d, shutting down", signum)
        worker.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    worker.start()


if __name__ == "__main__":
    main()
