"""P1.6 Worker — consume RabbitMQ, execute LangGraph with checkpoint, report progress.

The Worker:
1. Consumes JobCreated events from RabbitMQ (with idempotency).
2. Acquires a Redis lease for the job.
3. Builds the Phase 0 graph with MongoDBSaver checkpointer.
4. Invokes the graph with thread_id=job_id for crash recovery.
5. Streams progress events to Redis for SSE.
6. On completion/error, releases the lease and transitions MySQL status. The
   terminal verdict and the summary that justifies it are written by the same
   statement, and the "completed" stream frame is only emitted once that write
   was accepted — a row never announces a verdict it cannot back up.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.graph import build_phase0_graph
from agent.job_control import (
    CANCELLED_AT_CHECKPOINT,
    LEASE_LOST,
    ErrorClassification,
    JobCancelledError,
    LeaseLostError,
    classify_job_error,
    is_cancelled,
)
from agent.mongo_saver import MongoDBSaver
from agent.state import initial_state
from agent.worktree_reclaimer import reclaim_orphans
from evidence.verdict import evaluate_verification
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
        lease_max_hold: int | None = None,
    ) -> None:
        self.worker_id = worker_id or f"worker-{os.getpid()}-{int(time.time())}"
        self.lease_ttl = lease_ttl
        # §14.2 Redis 租约最大持有: 0/None = 传统无上限; 正数 = 总持有上限.
        self.lease_max_hold = (
            lease_max_hold if lease_max_hold and lease_max_hold > 0 else None
        )
        self.mysql = MySQLStore()
        self.redis = RedisStore()
        self.rabbitmq = RabbitMQClient()
        self._running = False
        self._compiled_graph: Any = None
        # Last pipeline stage whose completion chunk reached the stream loop
        # during the CURRENT job (single consumer callback ⇒ serial; reset at
        # the top of _handle_job_impl). The failure path reports it so the
        # row and the outward channels can say where the run died (#13.6-3).
        self._last_completed_stage: str | None = None

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

        # Stage provenance belongs to THIS run only — a previous job's last
        # stage must never be reported as where this one died.
        self._last_completed_stage = None

        # Acquire lease (prevents duplicate processing)
        if not self.redis.acquire_lease(
            job_id, self.worker_id, self.lease_ttl,
            max_hold_seconds=self.lease_max_hold,
        ):
            logger.info("Job %s already leased, skipping", job_id)
            return

        started = time.time()
        heartbeat_stop = threading.Event()
        lease_lost = threading.Event()
        heartbeat = threading.Thread(
            target=self._keep_lease, args=(job_id, heartbeat_stop, lease_lost),
            name=f"verify-lease-{job_id[:8]}", daemon=True,
        )
        heartbeat.start()
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
            if lease_lost.is_set():
                raise LeaseLostError(job_id, self.worker_id)
            self._check_stage_boundary(job_id, renew_lease=True)

            # Terminal status must reflect what the pipeline ACTUALLY found —
            # never an unconditional VERIFIED (a job with BLOCKER findings or
            # pipeline errors is not verified).
            verdict = _terminal_status_from_state(final_state)
            # The verdict and the evidence behind it are ONE write. Flipping
            # the row first and saving the summary afterwards let a reader
            # observe a completed job with no report, and made that state
            # permanent whenever the second write failed (it was suppressed).
            summary = _state_summary(final_state, verdict)
            if not self.mysql.transition_job_status(
                job_id, verdict, summary=summary
            ):
                # The CAS lost: the reclaimer, a cancel or the supervisor
                # already owns this row's status. This run's verdict is then
                # not the job's status, so nothing may be announced as done.
                logger.warning(
                    "Job %s terminal transition refused (row no longer ours for "
                    "worker %s) — verdict %s NOT announced as completion",
                    job_id, self.worker_id, verdict,
                )
                incr("worker_terminal_cas_lost_total")
                return
            with contextlib.suppress(Exception):
                # Observability (gauge = last job; histogram = p50/p95 SLO per
                # §14) and nothing else: a metrics backend being down must
                # never change what the job's durable record says.
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
            # Only reachable past the `if not written: return` gate above, so a
            # row this worker does not own gets no outward announcement from
            # either channel.
            self._maybe_notify_terminal(job_id, summary)
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
            reason_envelope: dict[str, Any] = {
                **classification.as_dict(), "error": str(exc)[:800],
            }
            if self._last_completed_stage:
                # Where the run died, as far as the stream can say: the last
                # stage whose completion chunk arrived. Persisted on the row
                # (last_error) so the outward channels inherit a fact, not a
                # re-derivation (#13.6-3).
                reason_envelope["failed_after_stage"] = self._last_completed_stage
            reason = json.dumps(reason_envelope, ensure_ascii=False)[:1024]
            # Backlog #5: a retryable provider outage parks the job in
            # WAITING_FOR_PROVIDER (audited) instead of failing it — the
            # recover path later moves it back to QUEUED, or to FAILED once
            # the retry budget is spent. Everything else keeps the FAILED
            # terminal path.
            provider_wait = self._provider_wait_allowed(job_id, classification)
            # The progress frame and the Check Run are announcements of a
            # stored outcome, not the outcome. They used to run first and
            # unconditionally, so the stream said "failed" for a job whose row
            # was parked in WAITING_FOR_PROVIDER, and a row already owned by a
            # cancel or a reclaimer (CAS refused) still got a failure frame
            # plus a GitHub Check Run concluding failure.
            written = False
            with contextlib.suppress(InvalidStateTransition):
                if provider_wait:
                    written = self.mysql.enter_provider_wait(
                        job_id, worker_id=self.worker_id, error_msg=reason,
                    )
                    if written:
                        incr("worker_provider_wait_total")
                else:
                    written = self.mysql.transition_job_status(
                        job_id, "FAILED", error_msg=reason
                    )
            if not written:
                logger.warning(
                    "Job %s failure transition refused (row no longer ours for "
                    "worker %s) — no failure announced",
                    job_id, self.worker_id,
                )
                incr("worker_terminal_cas_lost_total")
                return
            self.redis.xadd_progress(
                job_id, "terminal",
                "waiting_for_provider" if provider_wait else "failed",
                message=reason, percent=0.0,
            )
            # GitHub-sourced jobs must not stay in_progress forever. A
            # parked (provider-wait) job keeps its in-progress Check Run:
            # the retried run completes it honestly.
            if not provider_wait:
                # ONE summary for both outward channels, so a Check Run and a
                # notification cannot report the same failure differently.
                failure_summary = _failure_summary(
                    exc, classification,
                    failed_after_stage=self._last_completed_stage,
                )
                self._maybe_publish_github_check(
                    job_id, "FAILED", failure_summary
                )
                self._maybe_notify_terminal(job_id, failure_summary)
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=max(1.0, self.lease_ttl / 3))
            self.redis.release_lease(job_id, self.worker_id)

    def _keep_lease(
        self, job_id: str, stop: threading.Event, lost: threading.Event,
    ) -> None:
        """Long model calls must not outlive a lease renewed only between stages."""
        while not stop.wait(max(0.05, self.lease_ttl / 3)):
            try:
                if is_cancelled(job_id, self.mysql):
                    return
                if not self.redis.renew_lease(job_id, self.worker_id, self.lease_ttl):
                    lost.set()
                    return
            except Exception:
                lost.set()
                logger.warning("Lease heartbeat failed for job %s", job_id)
                return

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
                # Stage provenance for the failure path: this chunk names a
                # stage that just finished, so an exception later in the run
                # can be reported as "died after this stage" (#13.6-3).
                self._last_completed_stage = stage
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

    def _provider_wait_allowed(
        self, job_id: str, classification: ErrorClassification,
    ) -> bool:
        """True when a retryable provider outage should park the job.

        Only provider-class, retryable failures qualify (429/5xx per
        classify_job_error), and only while the job's own retry budget
        (retry_count < max_retries) still holds — an exhausted budget fails
        the job instead of parking it.
        """
        if classification.cls != "provider" or not classification.retryable:
            return False
        row = self.mysql.get_job(job_id) or {}
        retry_count = int(row.get("retry_count") or 0)
        max_retries_raw = row.get("max_retries")
        max_retries = int(max_retries_raw) if max_retries_raw is not None else 3
        return retry_count < max_retries

    def _persisted_status(self, job_id: str) -> str | None:
        """Best-effort read of the row's current status (None when unreadable).

        This is how a refused CAS can still narrate the truth: a stop frame
        may only carry a status the persisted row actually has — either
        because this write landed, or because the row was read back. A read
        failure means the row state is unknown, so nothing may be narrated.
        """
        try:
            row = self.mysql.get_job(job_id)
        except Exception:
            logger.warning(
                "Job %s: row read-back failed — row state unknown", job_id,
                exc_info=True,
            )
            return None
        if not row:
            return None
        status = str(row.get("status") or "").strip()
        return status or None

    def _mark_cancelled_at_checkpoint(self, job_id: str) -> None:
        """Mark the job CANCELLED with reason 'cancelled_at_checkpoint'.

        The API's cancel CAS usually owns the CANCELLED row already; this
        CAS is the worker's best-effort race-winner (row still RUNNING).
        The frame narrates the row, not the intention (#66): it says
        "cancelled" only when this write landed or a read-back confirms
        CANCELLED, and the audit row records the checkpoint reason under
        exactly the same condition. A row that confirms neither gets no
        frame, no audit — just a counter. Nothing else is written — a
        cancelled job gets no further side effects.
        """
        written = False
        try:
            written = self.mysql.transition_job_status(
                job_id, "CANCELLED", from_status="RUNNING",
                worker_id=self.worker_id, error_msg=CANCELLED_AT_CHECKPOINT,
            )
        except Exception:
            logger.warning(
                "Job %s: cancel transition at checkpoint raised — reading back",
                job_id, exc_info=True,
            )
        if not written:
            status = self._persisted_status(job_id)
            if status != "CANCELLED":
                logger.warning(
                    "Job %s: checkpoint cancel not confirmed on the row "
                    "(status=%s) — no cancel frame narrated", job_id, status,
                )
                incr("worker_cancel_checkpoint_unconfirmed_total")
                return
            # The API's cancel CAS won the race, and the row confirms it:
            # the checkpoint reason is still this worker's fact to record.
        try:
            self.mysql.record_audit(
                action="job_cancelled_at_checkpoint", actor=self.worker_id,
                job_id=job_id, from_status="RUNNING", to_status="CANCELLED",
                detail=CANCELLED_AT_CHECKPOINT,
            )
        except Exception:
            logger.warning(
                "Job %s: checkpoint-cancel audit could not be written",
                job_id, exc_info=True,
            )
        self.redis.xadd_progress(
            job_id, "cancel_checkpoint", "cancelled",
            message=CANCELLED_AT_CHECKPOINT, percent=0.0,
        )

    def _mark_lease_lost(self, job_id: str) -> None:
        """Fail fast on lease loss: FAILED with reason 'lease_lost'.

        No summary, billing end or GitHub check — the worker no longer owns
        the job, so it must stop writing business results. The frame follows
        the row (#66): this write's success narrates FAILED; a refused CAS
        reads the row back — the reclaimer may already have requeued the job
        (QUEUED: a retry is coming, "failed" would be a lie) or the user may
        have cancelled it — and narrates what the row actually says. When
        the row cannot be read, nothing is narrated and a counter records
        the silence.
        """
        written = False
        try:
            written = self.mysql.transition_job_status(
                job_id, "FAILED", from_status="RUNNING", error_msg=LEASE_LOST,
            )
        except Exception:
            logger.warning(
                "Job %s: lease-lost transition raised — reading back",
                job_id, exc_info=True,
            )
        status = "FAILED" if written else self._persisted_status(job_id)
        if status is None:
            logger.warning(
                "Job %s: lease lost but the row state could not be confirmed "
                "— no stop frame narrated", job_id,
            )
            incr("worker_lease_lost_unconfirmed_total")
            return
        self.redis.xadd_progress(
            job_id, "lease", status.lower(), message=LEASE_LOST, percent=0.0,
        )

    def _maybe_notify_terminal(self, job_id: str, summary: dict[str, Any]) -> None:
        """Best-effort outbound notification for a terminal verdict.

        The mirror of :meth:`_maybe_publish_github_check`, and it exists
        because ``integrations/notify/`` shipped a connector, three payload
        dialects and a template suite with a production call-site count of
        zero — capability that only looked wired because it was tested.

        Two deliberate choices:

        * The verdict is read out of the same ``summary`` object the row just
          persisted, not passed as a second argument. A verdict parameter
          would be a second source for one fact, and the two outward renderers
          (Check Run and notification) would then be able to disagree about
          what the job concluded.
        * An unsupported terminal verdict is declined on purpose, loudly, with
          a counter. :func:`integrations.notify.templates._require_terminal`
          raises ``ValueError`` for CANCELLED / ERROR / STALE, and catching
          that as "nothing to do" would lose the notification AND the fact
          that it was declined.

        Never raises: a delivery problem cannot flip a job that already
        reached its honest terminal state.
        """
        try:
            from integrations.notify import (
                build_terminal_notification,
                notifiable,
                webhook_connector_from_env,
            )

            verdict = str(summary.get("verdict", ""))
            if not notifiable(verdict):
                logger.info(
                    "Job %s: terminal verdict %r has no notification template; "
                    "nothing sent", job_id, verdict,
                )
                incr("notify_skipped_total")
                return
            connector = webhook_connector_from_env()
            try:
                status = connector.send(
                    build_terminal_notification(job_id, summary)
                )
            finally:
                # The factory returns a connector that owns an HTTP client and
                # this worker is a long-lived process: not closing it leaks one
                # client per announced job.
                connector.close()
            incr("notify_" + status.value + "_total")
        except Exception as exc:  # noqa: BLE001 — best effort
            logger.warning(
                "Terminal notification failed for %s: %s", job_id, exc
            )
            incr("notify_error_total")

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


#: Matrix row keys the web matrix view renders. Persisting exactly this
#: projection (rather than the whole row) keeps the audit summary readable
#: while still carrying the Base/Head differential attribution, which is the
#: single most actionable evidence a reviewer looks at.
_SUMMARY_MATRIX_ROW_KEYS: tuple[str, ...] = (
    "contract_id",
    "requirement",
    "checker_type",
    "result",
    "experiment",
    "evidence",
    "attribution",
    "base_result",
    "head_result",
    "unverified_reason",
    "next_action",
    "severity",
    "evidence_type",
    "location",
    "finding_id",
    # Where a differential experiment actually executed (container sandbox vs
    # the host with no sandbox). Carried so the coverage page can disclose it.
    "execution_surface",
)

#: Rows carried per job. The pipeline counts stay authoritative regardless, so
#: a cap can never under-report totals — see ``matrix_rows_total``.
SUMMARY_MATRIX_ROW_CAP = 60

#: Truncation ceiling for free-text cells inside a persisted matrix row.
_SUMMARY_TEXT_LIMIT = 400


def _matrix_rows_for_summary(
    matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project the evidence matrix into the persisted job summary.

    ``build_matrix`` produces one row per contract carrying the merge of every
    experiment that touched it, including the Base/Head differential verdict.
    Before this, only the COUNTS reached the API, so the "requirement coverage"
    page was empty for every real job and the per-requirement verdict was
    visible only in the HTML report. Rows are capped and the cap is reported,
    so a long matrix is honest ("showing N of M") rather than silently short.
    """
    rows = (matrix or {}).get("rows")
    if not isinstance(rows, list):
        return {"matrix_rows": [], "matrix_rows_total": 0, "matrix_rows_truncated": False}

    kept: list[dict[str, Any]] = []
    for row in rows[:SUMMARY_MATRIX_ROW_CAP]:
        if not isinstance(row, dict):
            continue
        projected: dict[str, Any] = {}
        for key in _SUMMARY_MATRIX_ROW_KEYS:
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, str) and len(value) > _SUMMARY_TEXT_LIMIT:
                value = value[:_SUMMARY_TEXT_LIMIT] + "…"
            projected[key] = value
        if str(projected.get("contract_id") or "").strip():
            kept.append(projected)

    total = int((matrix or {}).get("total_rows") or len(rows))
    return {
        "matrix_rows": kept,
        "matrix_rows_total": total,
        "matrix_rows_truncated": total > len(kept),
    }


def _failure_summary(
    exc: BaseException, classification: ErrorClassification,
    failed_after_stage: str | None = None,
) -> dict[str, Any]:
    """What a FAILED job can honestly put in front of an external channel.

    It carries no contract-count keys on purpose. `_state_summary` derives
    them from a finished pipeline state; a job that died mid-run never built a
    matrix, so the numbers were not zero — they were never computed. This call
    site used to hand the renderer literal zeros, which GitHub then published
    as `Contracts: 0 total — 0 passed, 0 failed, 0 unverified.`

    `failed_after_stage` records the last pipeline stage whose completion
    chunk reached the stream before the exception — the stream's only
    observation of "where it died" (None when it died before any stage
    finished, and then the key is absent, not empty: renderers treat an
    absent key as nothing to say).
    """
    summary: dict[str, Any] = {
        "verdict": "FAILED",
        "errors": [
            f"[{classification.cls}/{classification.code}] {str(exc)[:300]}"
        ],
    }
    if failed_after_stage:
        summary["failed_after_stage"] = failed_after_stage
    return summary


def _state_summary(state: dict[str, Any], verdict: str) -> dict[str, Any]:
    """Compact pipeline summary persisted for the dashboard/audit view."""
    matrix = state.get("matrix", {})
    findings = state.get("confirmed_findings", [])
    decision = evaluate_verification(
        matrix, contracts=state.get("contracts"), findings=findings,
        errors=state.get("errors", []),
    )
    return {
        "verdict": verdict,
        "contracts_total": len(state.get("contracts", [])),
        "matrix_passed": decision.passed,
        "matrix_failed": decision.failed,
        "matrix_unverified": decision.unverified,
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
        **_matrix_rows_for_summary(matrix),
        "report_path": state.get("report_path", ""),
        "retrieval_note": state.get("retrieval_note", ""),
        "coverage_reason": decision.reason,
        "errors": list(state.get("errors", []))[:10],
        # Phase 1.4: structured toolchain probes (checks/warnings/skipped).
        # Kept separate from `errors` so the UI can render "what we checked"
        # rather than only "what went wrong".
        "preflight": state.get("preflight", {}),
    }


def _terminal_status_from_state(state: dict[str, Any]) -> str:
    """Map the pipeline's honest result onto the MySQL job state machine.

    - FAILED   pipeline recorded errors (bad refs, missing spec, Maven errors)
    - BLOCKED  any confirmed finding, or contracts left UNVERIFIED: a human
               must look before merge — VERIFIED must never be fabricated
    - VERIFIED every contract passed with evidence and zero findings
    """
    return evaluate_verification(
        state.get("matrix"), contracts=state.get("contracts"),
        findings=state.get("confirmed_findings", []), errors=state.get("errors", []),
    ).status


# ── Standalone reclaimers (backlog #5, §14.1) ───────────────────

#: Queue the worker consumes; redeliveries use the same routing key the
#: outbox relay publishes JobCreated events with.
VERIFY_JOB_ROUTING_KEY = "q.p1.verify.job"


def _redeliver_job(job: dict[str, Any], attempt: int) -> None:
    """Re-publish one JobCreated event for a reclaimed/recovered job.

    The event_id embeds the retry attempt so the worker's Redis idempotency
    gate accepts the redelivery as a NEW event (the original event_id was
    already consumed). Raises on broker failure — callers decide whether a
    failed redelivery aborts them (the MySQL transition has already been
    audited either way).
    """
    rabbitmq = RabbitMQClient()
    try:
        rabbitmq.publish(
            VERIFY_JOB_ROUTING_KEY,
            {
                "job_id": job["id"],
                "repo_path": job.get("repo_path", ""),
                "base_ref": job.get("base_ref", ""),
                "head_ref": job.get("head_ref", ""),
                "spec_path": job.get("spec_path", ""),
                "depth": job.get("depth", "FAST"),
                "event_id": f"retry-{job['id']}-{attempt}",
            },
        )
    finally:
        rabbitmq.close()


def reclaim_stale_running_jobs(lease_ttl_seconds: int = 30) -> list[dict[str, Any]]:
    """Standalone RUNNING-job reclaimer: lease-expired, heartbeat-less → QUEUED.

    Wires MySQLStore.reclaim_stale_running (CAS: status=RUNNING AND
    updated_at < now-ttl, per-job audit) to the Redis lease key as the
    heartbeat probe — ``RedisStore.get_lease_owner`` returns None exactly
    when the lease expired or was never renewed. Each reclaimed job is
    re-delivered to q.p1.verify.job with a fresh event_id (best-effort;
    the audited QUEUED transition stands even if the broker is down).

    Returns the reclaimed job rows (post-reclaim retry_count), or [] when
    nothing was stale.
    """
    store = MySQLStore()
    redis = RedisStore()
    reclaimed = store.reclaim_stale_running(
        lease_ttl_seconds,
        lease_alive=lambda job_id: redis.get_lease_owner(job_id) is not None,
    )
    for row in reclaimed:
        attempt = int(row.get("retry_count") or 1)
        try:
            _redeliver_job(row, attempt)
            logger.info(
                "Job %s reclaimed (stale RUNNING, lease lost) and re-queued",
                row["id"],
            )
        except Exception as exc:  # noqa: BLE001 — MySQL transition stands
            logger.warning(
                "Job %s reclaimed but re-delivery failed: %s", row["id"], exc
            )
    redis.close()
    store.close()
    return reclaimed


def recover_waiting_for_provider_jobs(
    *,
    provider_ready: Callable[[], bool] | None = None,
) -> list[tuple[str, str]]:
    """Recover WAITING_FOR_PROVIDER jobs: QUEUED under budget, FAILED over it.

    For each WAITING_FOR_PROVIDER row, MySQLStore.recover_provider_wait
    moves it to QUEUED (retry_count+1) while the job's retry budget holds,
    or to FAILED once retry_count >= max_retries. QUEUED outcomes are
    re-delivered to q.p1.verify.job with a fresh event_id. When a
    provider_ready probe is supplied (e.g. a CircuitBreaker state check),
    jobs stay parked until it reports True.

    Returns [(job_id, new_status), ...] for every recovered job.
    """
    if provider_ready is not None and not provider_ready():
        logger.info("Provider not ready; WAITING_FOR_PROVIDER jobs stay parked")
        return []
    store = MySQLStore()
    results: list[tuple[str, str]] = []
    for row in store.get_jobs_by_status("WAITING_FOR_PROVIDER"):
        job_id = str(row["id"])
        changed, new_status = store.recover_provider_wait(job_id)
        if not changed or new_status is None:
            continue
        results.append((job_id, new_status))
        if new_status == "QUEUED":
            attempt = int(row.get("retry_count") or 0) + 1
            try:
                _redeliver_job(row, attempt)
                logger.info(
                    "Job %s recovered from provider wait and re-queued", job_id
                )
            except Exception as exc:  # noqa: BLE001 — MySQL transition stands
                logger.warning(
                    "Job %s recovered but re-delivery failed: %s", job_id, exc
                )
        else:
            logger.warning(
                "Job %s provider-wait retry budget spent -> FAILED", job_id
            )
    store.close()
    return results


# ── Standalone projection cleanup (backlog #10, DATA_LIFECYCLE §3.4) ──


def cleanup_job_projection(job_id: str) -> int:
    """Delete one job's Elasticsearch retrieval projection (backlog #10).

    Retrieval projections are audit evidence, so they deliberately survive
    the job's terminal transition (VERIFIED/BLOCKED/FAILED/CANCELLED/
    ERROR/STALE) — this entry is NOT wired into the worker terminal path.
    Call it from the data-lifecycle job deletion (DATA_LIFECYCLE.md §3.4)
    when the verification_jobs row is removed (or during tenant deletion):
    it deletes every ES doc stamped with this job_id via
    ElasticsearchStore.delete_projection.

    Idempotent: a missing index or missing documents return 0, so a
    second call for the same job is a no-op. Best-effort: an unavailable
    Elasticsearch is logged and reported as 0, never raised.
    """
    if not job_id:
        logger.warning("cleanup_job_projection called without a job_id — no-op")
        return 0
    from storage.elasticsearch import ElasticsearchStore

    store = ElasticsearchStore()
    try:
        deleted = store.delete_projection(job_id=job_id)
        logger.info("Job %s: deleted %d projection docs", job_id, deleted)
        return deleted
    except Exception as exc:  # noqa: BLE001 — cleanup is best-effort
        logger.warning("Job %s: projection cleanup failed: %s", job_id, exc)
        return 0
    finally:
        store.close()


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
