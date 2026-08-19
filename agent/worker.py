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
import tempfile
import time
from pathlib import Path
from typing import Any

from agent.graph import build_phase0_graph
from agent.job_control import (
    CANCELLED_AT_CHECKPOINT,
    LEASE_LOST,
    JobCancelledError,
    LeaseLostError,
    classify_job_error,
    is_cancelled,
)
from agent.mongo_saver import MongoDBSaver
from agent.state import initial_state
from agent.worktree_reclaimer import reclaim_orphans
from observability.metrics import incr, observe_duration, set_gauge
from storage.mysql import InvalidStateTransition, MySQLStore
from storage.rabbitmq import RabbitMQClient, make_idempotency_check
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
        """Register the job consumer on q.p1.verify.job.

        main() pumps the blocking connection with start_consuming() right
        after this call; deliveries are not processed until then. The
        idempotency check follows the consumer contract (True = duplicate)
        via storage.rabbitmq.make_idempotency_check — passing
        RedisStore.set_idempotent directly would invert the boolean and
        silently drop every message as a "duplicate".
        """
        self._running = True
        self.rabbitmq.ensure_topology()

        logger.info("Worker %s starting consumption", self.worker_id)
        self.rabbitmq.consume_with_policy(
            queue="q.p1.verify.job",
            callback=self._handle_job,
            policy=None,
            idempotency_fn=make_idempotency_check(self.redis),
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

            # Billing metering (industrialization phase 6, BILLING_DESIGN.md
            # §2): one job_verify unit when the pipeline actually starts.
            # Best-effort and opt-in — no SPECPROOF_BILLING_URL means the
            # writer is None and this block is a byte-identical no-op; the
            # tenant id comes from the job row (the outbox payload has none).
            with contextlib.suppress(Exception):
                from storage.billing import meter_verify_job_start

                started_row = self.mysql.get_job(job_id)
                started_tenant = str((started_row or {}).get("tenant_id") or "")
                if started_tenant:
                    meter_verify_job_start(started_tenant, job_id)

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
                incr("jobs_completed_total")
                incr("jobs_" + verdict.lower() + "_total")
                set_gauge("jobs_processing_seconds", float(time.time() - started))
                observe_duration(
                    "jobs_duration_seconds", float(time.time() - started)
                )
            # Billing metering: gate_findings units = confirmed findings at
            # the terminal transition (idempotent event_id — a crash-recovery
            # replay of the same job cannot double-count). Same opt-in
            # best-effort envelope as the start hook.
            with contextlib.suppress(Exception):
                from storage.billing import meter_verify_job_end

                ended_row = self.mysql.get_job(job_id)
                ended_tenant = str((ended_row or {}).get("tenant_id") or "")
                ended_findings = len(summary.get("findings", []))
                if ended_tenant and ended_findings > 0:
                    meter_verify_job_end(
                        ended_tenant, job_id, ended_findings, verdict,
                    )
            self._maybe_publish_github_check(
                job_id, verdict, summary, final_state
            )
            self.redis.xadd_progress(job_id, "publish_report", "completed",
                                     message=f"Job completed: {verdict}", percent=100.0)

        except InvalidStateTransition:
            logger.warning("Job %s state transition failed, may be stale", job_id)
        except JobCancelledError as exc:
            # §14 任务 8: cancellation checkpoint honored — mark CANCELLED
            # with reason 'cancelled_at_checkpoint' and stop. No summary,
            # no billing end, no GitHub check: no further side effects.
            logger.info(
                "Job %s cancelled at checkpoint %s — no further side effects",
                job_id, exc.stage,
            )
            self._mark_cancelled_at_checkpoint(job_id)
            incr("worker_cancelled_at_checkpoint_total")
        except LeaseLostError:
            # §14 任务 8: the worker no longer owns the lease — fail fast
            # with reason 'lease_lost' and stop writing business results.
            logger.error(
                "Job %s lost lease (worker %s) — stopping", job_id, self.worker_id
            )
            self._mark_lease_lost(job_id)
            incr("worker_lease_lost_total")
        except Exception as exc:
            # §14 任务 8: unified error classification written into the
            # terminal reason (last_error) and the progress events.
            classification = classify_job_error(exc)
            logger.error(
                "Job %s failed: [%s/%s] %s", job_id,
                classification.cls, classification.code, exc,
            )
            reason = json.dumps(
                {**classification.as_dict(), "error": str(exc)[:800]},
                ensure_ascii=False,
            )[:1024]
            self.redis.xadd_progress(job_id, job_id, "failed",
                                     message=reason, percent=0.0)
            with contextlib.suppress(InvalidStateTransition):
                self.mysql.transition_job_status(
                    job_id, "FAILED", error_msg=reason
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

        §14 任务 8: the stream runs in dual mode — "updates" chunks name the
        stage that just finished (per-stage duration metrics, cancellation
        checkpoint and lease renewal at the stage boundary); "values" chunks
        are the cumulative state snapshots, so the final chunk is the same
        complete state a single-mode values stream would produce.
        """
        state = initial_state(
            repo_path=payload.get("repo_path", ""),
            base_ref=payload.get("base_ref", "base"),
            head_ref=payload.get("head_ref", "head-v1"),
            spec_path=payload.get("spec_path", ""),
            depth=payload.get("depth", "FAST"),
        )
        # §A task 7: artifacts written by the pipeline record this job id
        # in the object metadata store (query by job_id later).
        state["job_id"] = job_id

        config = {"configurable": {"thread_id": job_id}}

        # Build the graph for this invocation (fresh checkpointer each time).
        saver = MongoDBSaver()

        # §14.1 crash reclaimer: a fresh job reclaims orphan worktrees left
        # by a crashed earlier run of the same job.  Resume paths skip this
        # — their worktrees are live checkpoint state, not orphans.
        self._reclaim_orphan_worktrees(saver, job_id)

        graph = build_phase0_graph(checkpointer=saver)

        # Cancellation checkpoint before the first stage: a cancel that
        # landed between lease acquisition and graph start must not execute
        # a single node. The lease was just acquired, so no renewal here.
        self._check_stage_boundary(job_id, renew_lease=False)

        final_state: dict[str, Any] = {}
        stage_started = time.monotonic()
        for item in graph.stream(
            state, config, stream_mode=["updates", "values"],
        ):
            mode, chunk = item
            if mode == "updates":
                stage = next(iter(chunk), "unknown") if chunk else "unknown"
                now = time.monotonic()
                observe_duration(
                    "worker_stage_duration_seconds_" + str(stage),
                    now - stage_started,
                )
                stage_started = now
                # Stage boundary: cancel checkpoint first (a cancelled job
                # must not keep renewing its lease), then lease renewal.
                self._check_stage_boundary(job_id, renew_lease=True)
            elif mode == "values":
                final_state = chunk

        # Final boundary (after publish_report): a cancel that landed during
        # the last stage must stop the terminal business writes.
        self._check_stage_boundary(job_id, renew_lease=True)

        with contextlib.suppress(Exception):
            self.redis.xadd_progress(
                job_id, "publish_report", "completed",
                message="Graph finished", percent=100.0,
            )

        return final_state

    def _reclaim_orphan_worktrees(self, saver: Any, job_id: str) -> None:
        """Reclaim orphan worktrees left by a crashed run of this job.

        Only a fresh start may reclaim: when a checkpoint already exists the
        graph resumes and reuses the worktrees recorded in state, so removing
        them would destroy live work.  When the checkpoint cannot be read the
        reclaim is skipped entirely (fail-safe against destroying data), and
        any reclamation failure never blocks the job.
        """
        try:
            existing = saver.get_tuple({"configurable": {"thread_id": job_id}})
        except Exception as exc:  # noqa: BLE001 — skip on uncertainty
            logger.warning(
                "Job %s: could not read checkpoint to decide worktree "
                "reclamation; skipping: %s", job_id, exc,
            )
            return
        if existing is not None:
            return
        try:
            result = reclaim_orphans(Path(tempfile.gettempdir()), job_id)
        except Exception as exc:  # noqa: BLE001 — never blocks the job
            logger.warning(
                "Job %s: orphan worktree reclamation failed: %s", job_id, exc,
            )
            return
        if (
            result.reclaimed
            or result.left_foreign
            or result.failures
            or result.warnings
        ):
            logger.info(
                "Job %s: orphan worktree reclaim: reclaimed=%d "
                "left_foreign=%d failures=%d warnings=%d",
                job_id, result.reclaimed, result.left_foreign,
                len(result.failures), len(result.warnings),
            )

    def _check_stage_boundary(self, job_id: str, *, renew_lease: bool) -> None:
        """Stage-boundary control: cancellation checkpoint + lease renewal.

        Cancel first: a cancelled job must not keep renewing its lease.
        Lease renewal (§14 任务 8): renew count and duration are exported
        through observability.metrics; a False renewal means another worker
        owns the lease (expired or taken over) — fail fast with reason
        'lease_lost' and stop writing business results.
        """
        if is_cancelled(job_id, self.mysql):
            raise JobCancelledError(job_id, "stage_boundary")
        if not renew_lease:
            return
        renew_started = time.monotonic()
        renewed = self.redis.renew_lease(job_id, self.worker_id, self.lease_ttl)
        incr("worker_lease_renews_total")
        observe_duration(
            "worker_lease_renew_seconds", time.monotonic() - renew_started
        )
        if not renewed:
            raise LeaseLostError(job_id, self.worker_id)

    def _mark_cancelled_at_checkpoint(self, job_id: str) -> None:
        """Mark the job CANCELLED with reason 'cancelled_at_checkpoint'.

        The API's cancel CAS usually owns the CANCELLED row already; this
        CAS is the worker's best-effort race-winner (row still RUNNING) and
        the audit row + progress event carry the checkpoint reason either
        way. Nothing else is written — a cancelled job gets no further side
        effects.
        """
        with contextlib.suppress(Exception):
            self.mysql.transition_job_status(
                job_id, "CANCELLED", from_status="RUNNING",
                worker_id=self.worker_id, error_msg=CANCELLED_AT_CHECKPOINT,
            )
            self.mysql.record_audit(
                action="job_cancelled_at_checkpoint", actor=self.worker_id,
                job_id=job_id, from_status="RUNNING", to_status="CANCELLED",
                detail=CANCELLED_AT_CHECKPOINT,
            )
        self.redis.xadd_progress(
            job_id, "cancel_checkpoint", "failed",
            message=CANCELLED_AT_CHECKPOINT, percent=0.0,
        )

    def _mark_lease_lost(self, job_id: str) -> None:
        """Fail fast on lease loss: FAILED with reason 'lease_lost'.

        No summary, billing end or GitHub check — the worker no longer owns
        the job, so it must stop writing business results.
        """
        with contextlib.suppress(Exception):
            self.mysql.transition_job_status(
                job_id, "FAILED", from_status="RUNNING", error_msg=LEASE_LOST,
            )
        self.redis.xadd_progress(
            job_id, "lease", "failed", message=LEASE_LOST, percent=0.0,
        )

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
    # Pump deliveries: the blocking connection only dispatches consumer
    # callbacks while start_consuming() runs. It returns when the
    # connection is lost (logged by RabbitMQClient), after which the
    # process exits non-zero so the launcher/supervisor can restart it.
    worker.rabbitmq.start_consuming()
    worker.stop()
    logger.error("RabbitMQ consumption loop ended — worker exiting")
    sys.exit(1)


if __name__ == "__main__":
    main()
