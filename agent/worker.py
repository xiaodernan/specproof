"""P1.6 Worker — consume RabbitMQ, execute LangGraph with checkpoint, report progress.

The Worker:
1. Consumes JobCreated events from RabbitMQ (with idempotency).
2. Acquires a Redis lease for the job.
3. Builds the Phase 0 graph with MongoDBSaver checkpointer.
4. Invokes the graph with thread_id=job_id for crash recovery.
5. Streams progress events to Redis for SSE.
6. On completion/error, releases the lease and transitions MySQL status.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from typing import Any

from agent.graph import build_phase0_graph
from agent.mongo_saver import MongoDBSaver
from agent.state import initial_state
from storage.mysql import MySQLStore, InvalidStateTransition
from storage.rabbitmq import RabbitMQClient
from storage.redis import RedisStore

logger = logging.getLogger(__name__)


class Worker:
    """Job executor with checkpoint-based crash recovery."""

    def __init__(
        self,
        worker_id: str | None = None,
        lease_ttl: int = 30,
    ) -> None:
        self.worker_id = worker_id or f"worker-{os.getpid()}-{int(time.time())}"
        self.lease_ttl = lease_ttl
        self.mysql = MySQLStore()
        self.redis = RedisStore()
        self.rabbitmq = RabbitMQClient()
        self._running = False
        self._compiled_graph = None

    @property
    def compiled_graph(self):
        if self._compiled_graph is None:
            saver = MongoDBSaver()
            self._compiled_graph = build_phase0_graph(checkpointer=saver)
        return self._compiled_graph

    # ── Public API ───────────────────────────────────────────────

    def start(self) -> None:
        """Start consuming jobs. Blocks until stop() is called."""
        self._running = True
        self.rabbitmq.ensure_topology()

        logger.info("Worker %s starting consumption", self.worker_id)
        self.rabbitmq.consume_with_policy(
            queue="q.p1.verify.job",
            callback=self._handle_job,
            policy=None,
            idempotency_fn=self.redis.set_idempotent,
        )

    def stop(self) -> None:
        self._running = False
        self.rabbitmq.close()
        self.redis.close()
        self.mysql.close()
        logger.info("Worker %s stopped", self.worker_id)

    def execute_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Run one job synchronously (for testing / direct invocation).

        Returns the final state dict.
        """
        return self._run_graph(job_id, payload)

    # ── Internal ─────────────────────────────────────────────────

    def _handle_job(self, payload: dict[str, Any]) -> None:
        """RabbitMQ callback: process one JobCreated event."""
        job_id = payload.get("job_id", "unknown")
        event_id = payload.get("event_id", "")

        if not self._running:
            return

        # Acquire lease (prevents duplicate processing)
        if not self.redis.acquire_lease(job_id, self.worker_id, self.lease_ttl):
            logger.info("Job %s already leased, skipping", job_id)
            return

        try:
            # Transition to RUNNING
            self.mysql.transition_job_status(job_id, "RUNNING", worker_id=self.worker_id)

            # Execute graph with checkpoint
            self._run_graph(job_id, payload)

            # Transition to terminal state
            self.mysql.transition_job_status(job_id, "VERIFIED")
            self.redis.xadd_progress(job_id, "publish_report", "completed",
                                     message="Job completed", percent=100.0)

        except InvalidStateTransition:
            logger.warning("Job %s state transition failed, may be stale", job_id)
        except Exception as exc:
            logger.error("Job %s failed: %s", job_id, exc)
            self.redis.xadd_progress(job_id, job_id, "failed",
                                     message=str(exc), percent=0.0)
            try:
                self.mysql.transition_job_status(
                    job_id, "FAILED", error_msg=str(exc)[:1024]
                )
            except InvalidStateTransition:
                pass
        finally:
            self.redis.release_lease(job_id, self.worker_id)

    def _run_graph(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the LangGraph pipeline with checkpoint recovery.

        The same thread_id is used for both initial runs and crash recovery.
        LangGraph's checkpointer automatically skips completed nodes when
        the graph is re-invoked with the same thread_id.
        """
        state = initial_state(
            repo_path=payload.get("repo_path", ""),
            base_ref=payload.get("base_ref", "base"),
            head_ref=payload.get("head_ref", "head-v1"),
            spec_path=payload.get("spec_path", ""),
            depth=payload.get("depth", "FAST"),
        )

        config = {"configurable": {"thread_id": job_id}}

        # Stream progress through a callback on each node transition
        last_node = ["start"]

        def _progress_callback(node_name: str):
            last_node[0] = node_name
            try:
                self.redis.xadd_progress(
                    job_id, node_name, "running",
                    message=f"Executing {node_name}", percent=0.0,
                )
            except Exception:
                pass

        # Build the graph for this invocation (fresh checkpointer each time)
        saver = MongoDBSaver()
        graph = build_phase0_graph(checkpointer=saver)

        try:
            # We use stream mode to get per-node progress
            final_state = None
            for chunk in graph.stream(state, config, stream_mode="values"):
                final_state = chunk

            if final_state:
                # Save final progress
                for node_name in [
                    "intake", "compile_contracts", "prepare_base", "prepare_head",
                    "collect_diff", "run_static_checks", "generate_counterexamples",
                    "run_differential", "review_court", "build_matrix",
                    "create_capsule", "publish_report",
                ]:
                    self.redis.xadd_progress(
                        job_id, node_name, "completed",
                        message="Done", percent=100.0,
                    )
                    break  # Only record the last node as completed for brevity

            return dict(final_state) if final_state else {}

        except Exception:
            # Crash during graph execution: checkpoint was already saved by
            # the checkpointer after each completed node. A subsequent
            # invocation with the same thread_id will resume.
            raise


def main():
    """CLI entry point for the Worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    worker = Worker()

    def _shutdown(signum, frame):
        logger.info("Received signal %d, shutting down", signum)
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    worker.start()


if __name__ == "__main__":
    main()
