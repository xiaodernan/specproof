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

import contextlib
import json
import logging
import os
import signal
import sys
import time
from typing import Any

from agent.graph import build_phase0_graph
from agent.mongo_saver import MongoDBSaver
from agent.state import initial_state
from storage.mysql import InvalidStateTransition, MySQLStore
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
        self._compiled_graph: Any = None

    @property
    def compiled_graph(self) -> Any:
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

        # Structured-logging context: every line inside this handler carries
        # the job_id, correlating worker logs with the job timeline.
        from observability.logging import job_id_var

        token = job_id_var.set(job_id)
        try:
            self._handle_job_impl(job_id, payload)
        finally:
            job_id_var.reset(token)

    def _handle_job_impl(self, job_id: str, payload: dict[str, Any]) -> None:
        if not self._running:
            return

        # Acquire lease (prevents duplicate processing)
        if not self.redis.acquire_lease(job_id, self.worker_id, self.lease_ttl):
            logger.info("Job %s already leased, skipping", job_id)
            return

        started = time.time()
        try:
            # Transition to RUNNING
            self.mysql.transition_job_status(job_id, "RUNNING", worker_id=self.worker_id)

            # Execute graph with checkpoint
            final_state = self._run_graph(job_id, payload)

            # Terminal status must reflect what the pipeline ACTUALLY found —
            # never an unconditional VERIFIED (a job with BLOCKER findings or
            # pipeline errors is not verified).
            verdict = _terminal_status_from_state(final_state)
            self.mysql.transition_job_status(job_id, verdict)
            summary: dict[str, Any] = {}
            with contextlib.suppress(Exception):
                summary = _state_summary(final_state, verdict)
                self.mysql.save_job_summary(job_id, summary)
                # Observability: completion counter + processing duration
                # (gauge = last job; histogram = p50/p95 SLO per §14).
                from observability.metrics import incr, observe_duration, set_gauge

                incr("jobs_completed_total")
                incr("jobs_" + verdict.lower() + "_total")
                set_gauge("jobs_processing_seconds", float(time.time() - started))
                observe_duration(
                    "jobs_duration_seconds", float(time.time() - started)
                )
            self._maybe_publish_github_check(
                job_id, verdict, summary, final_state
            )
            self.redis.xadd_progress(job_id, "publish_report", "completed",
                                     message=f"Job completed: {verdict}", percent=100.0)

        except InvalidStateTransition:
            logger.warning("Job %s state transition failed, may be stale", job_id)
        except Exception as exc:
            logger.error("Job %s failed: %s", job_id, exc)
            self.redis.xadd_progress(job_id, job_id, "failed",
                                     message=str(exc), percent=0.0)
            with contextlib.suppress(InvalidStateTransition):
                self.mysql.transition_job_status(
                    job_id, "FAILED", error_msg=str(exc)[:1024]
                )
            # GitHub-sourced jobs must not stay in_progress forever.
            self._maybe_publish_github_check(
                job_id, "FAILED",
                {
                    "verdict": "FAILED",
                    "contracts_total": 0,
                    "findings": [],
                    "errors": [str(exc)[:200]],
                },
            )
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

        # Build the graph for this invocation (fresh checkpointer each time).
        # Stream mode yields the state after every node; the final chunk is
        # the complete state after publish_report.
        saver = MongoDBSaver()
        graph = build_phase0_graph(checkpointer=saver)

        final_state: dict[str, Any] = {}
        for chunk in graph.stream(state, config, stream_mode="values"):
            final_state = chunk

        with contextlib.suppress(Exception):
            self.redis.xadd_progress(
                job_id, "publish_report", "completed",
                message="Graph finished", percent=100.0,
            )

        return final_state

    def _maybe_publish_github_check(
        self,
        job_id: str,
        verdict: str,
        summary: dict[str, Any],
        final_state: dict[str, Any] | None = None,
    ) -> None:
        """Best-effort Check Run completion for GitHub-sourced jobs.

        Never raises: an optional GitHub integration must not flip a job
        that already reached its honest terminal state.

        For BLOCKED jobs sourced from a pull_request webhook, the terminal
        update is followed by Inline Finding review comments (spec 6.2
        "Inline Findings", capped at INLINE_MAX) anchored to real head-file
        lines via integrations.inline_comments.
        """
        try:
            job = self.mysql.get_job(job_id)
            meta_raw = (job or {}).get("github_check_json")
            if not meta_raw:
                return
            meta = (
                json.loads(meta_raw)
                if isinstance(meta_raw, str)
                else meta_raw
            )
            from integrations.github_checks import (
                GitHubAppConfigError,
                check_summary_text,
                conclusion_for_verdict,
                github_app_client_from_env,
            )

            try:
                client = github_app_client_from_env()
            except GitHubAppConfigError as exc:
                logger.warning("GitHub App misconfigured: %s", exc)
                return
            if client is None:
                logger.info(
                    "GitHub App not configured; check run not updated"
                )
                return
            with client:
                client.update_check_run(
                    check_run_id=int(meta["check_run_id"]),
                    owner=str(meta["owner"]),
                    repo=str(meta["repo"]),
                    conclusion=conclusion_for_verdict(verdict),
                    title="SpecProof: " + verdict,
                    summary=check_summary_text(verdict, summary),
                )
                self._maybe_publish_inline_findings(
                    job_id, client, meta, verdict, summary, final_state
                )
        except Exception as exc:  # noqa: BLE001 — best effort
            logger.warning(
                "GitHub check run update failed for %s: %s", job_id, exc
            )

    def _maybe_publish_inline_findings(
        self,
        job_id: str,
        client: Any,
        meta: dict[str, Any],
        verdict: str,
        summary: dict[str, Any],
        final_state: dict[str, Any] | None,
    ) -> None:
        """Best-effort Inline Finding review comments on a BLOCKED PR job.

        Runs inside the same best-effort envelope as the Check Run update:
        any failure is logged, never raised.
        """
        if verdict != "BLOCKED" or final_state is None:
            return
        pull_number = meta.get("pull_number")
        if not pull_number:
            return
        from integrations.inline_comments import build_review_comments

        diff_by_file = final_state.get("diff_by_file") or {}
        if not diff_by_file:
            return
        comments = build_review_comments(
            summary.get("findings", []), diff_by_file
        )
        if not comments:
            return
        client.publish_inline_findings(
            owner=str(meta["owner"]),
            repo=str(meta["repo"]),
            pull_number=int(pull_number),
            commit_id=str(meta["head_sha"]),
            comments=comments,
        )
        logger.info(
            "Published %d inline findings for %s", len(comments), job_id
        )


def _state_summary(state: dict[str, Any], verdict: str) -> dict[str, Any]:
    """Compact pipeline summary persisted for the dashboard/audit view."""
    matrix = state.get("matrix", {})
    findings = state.get("confirmed_findings", [])
    return {
        "verdict": verdict,
        "contracts_total": len(state.get("contracts", [])),
        "matrix_passed": matrix.get("passed", 0),
        "matrix_failed": matrix.get("failed", 0),
        "matrix_unverified": matrix.get("unverified", 0),
        "findings": [
            {
                "id": f.get("id"),
                "severity": f.get("severity"),
                "contract_id": f.get("contract_id"),
                "confidence": f.get("confidence"),
                "evidence_type": f.get("evidence_type"),
                "type": f.get("type", ""),
                "location": f.get("location", ""),
                "description": (f.get("description") or "")[:400],
            }
            for f in findings[:20]
        ],
        "capsules": [str(c) for c in state.get("capsules", [])[:10]],
        "report_path": state.get("report_path", ""),
        "retrieval_note": state.get("retrieval_note", ""),
        "errors": list(state.get("errors", []))[:10],
    }


def _terminal_status_from_state(state: dict[str, Any]) -> str:
    """Map the pipeline's honest result onto the MySQL job state machine.

    - FAILED   pipeline recorded errors (bad refs, missing spec, Maven errors)
    - BLOCKED  any confirmed finding, or contracts left UNVERIFIED: a human
               must look before merge — VERIFIED must never be fabricated
    - VERIFIED every contract passed with evidence and zero findings
    """
    if state.get("errors"):
        return "FAILED"
    findings = state.get("confirmed_findings", [])
    if findings:
        return "BLOCKED"
    matrix = state.get("matrix", {})
    if matrix.get("unverified", 0) > 0:
        return "BLOCKED"
    return "VERIFIED"


def main() -> None:
    """CLI entry point for the Worker."""
    from observability.logging import configure_logging
    from observability.tracing import init_tracing

    configure_logging()
    init_tracing(service_name="specproof-worker")

    # P6: worker 进程内 /metrics (Prometheus 抓取目标 worker:9100)。
    # 纯 stdlib 守护线程; 端口可用 WORKER_METRICS_PORT 覆盖。
    from observability.metrics_http import serve_metrics_in_thread

    serve_metrics_in_thread(port=int(os.getenv("WORKER_METRICS_PORT", "9100")))

    worker = Worker()

    def _shutdown(signum: int, frame: Any) -> None:
        logger.info("Received signal %d, shutting down", signum)
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    worker.start()


if __name__ == "__main__":
    main()
