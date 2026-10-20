"""Verification application service (Phase 1, P1-6).

Single service layer that every entry point (CLI, FastAPI, MCP, Web) uses
for verification job operations. Routes call this service instead of
instantiating ``MySQLStore`` directly, so all entry points share the same
state machine, audit trail, and idempotency guarantees.

The service is a thin translation layer: it validates input, delegates to
``MySQLStore`` for durable writes, and returns plain dicts (never ORM
models) so callers remain storage-agnostic.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

from api.errors import (
    JOB_NOT_FOUND,
    PROVIDER_UNAVAILABLE,
    STATE_CONFLICT,
    ApiError,
)
from storage.mysql import ALL_STATUSES, MySQLStore


class VerificationApplicationService:
    """Single source of truth for verification job lifecycle operations."""

    def __init__(self, store: MySQLStore | None = None) -> None:
        self._store = store or MySQLStore()

    # ── Job creation ──────────────────────────────────────────────

    def create_job(
        self,
        *,
        repo_path: str,
        base_ref: str,
        head_ref: str,
        spec_path: str,
        depth: str = "FAST",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a verification job with Outbox event (one transaction).

        Returns the created job dict. Raises ``ApiError`` 503 if the store
        is unavailable; never pretends a job was accepted when it was not
        persisted.
        """
        # Validate status filter values are from the single source of truth.
        if depth not in ("FAST", "DEEP"):
            raise ApiError(
                status_code=422,
                code="VALIDATION_FAILED",
                detail=f"Unsupported depth: {depth!r}. Supported: FAST, DEEP.",
            )

        job_id = idempotency_key or str(uuid.uuid4())
        try:
            created_id = self._store.create_job_with_outbox({
                "id": job_id,
                "repo_path": repo_path,
                "base_ref": base_ref,
                "head_ref": head_ref,
                "spec_path": spec_path,
                "depth": depth,
            })
        except Exception as exc:  # noqa: BLE001 — MySQL down / schema missing
            raise ApiError(
                status_code=503,
                code=PROVIDER_UNAVAILABLE,
                detail=(
                    "Job NOT accepted — the verification job store is "
                    "unavailable. Web Verify needs MySQL/Redis backing "
                    "services; in zero-Docker light mode run the CLI "
                    "(`specproof verify`) instead, or start the services."
                ),
            ) from exc
        # The service returns the CREATE RESPONSE shape, not the job row:
        # the row's own id field is named "id", and the API contract names
        # it "job_id" on the wire. Returning the row here would make the
        # route read a key that does not exist.
        row = self.get_job(created_id)
        return {
            "job_id": created_id,
            "status": str((row or {}).get("status") or "QUEUED"),
        }

    # ── Job query ─────────────────────────────────────────────────

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return one job's status from MySQL (the business source of truth)."""
        try:
            return self._store.get_job(job_id)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                status_code=503,
                code=PROVIDER_UNAVAILABLE,
                detail=f"MySQL unavailable: {exc}",
            ) from exc

    def require_job(self, job_id: str) -> dict[str, Any]:
        """Return a job or raise 404 JOB_NOT_FOUND."""
        job = self.get_job(job_id)
        if job is None:
            raise ApiError(
                status_code=404,
                code=JOB_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )
        return job

    def list_jobs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        q: str = "",
    ) -> dict[str, Any]:
        """List the most recent verification jobs.

        ``status`` is validated against ``ALL_STATUSES`` (the single source
        of truth) — an unknown word raises 422 rather than silently
        matching nothing.
        """
        if status is not None and status not in ALL_STATUSES:
            raise ApiError(
                status_code=422,
                code="VALIDATION_FAILED",
                detail=f"Unknown job status filter: {status!r}",
            )
        try:
            return self._store.search_jobs(limit, offset, status, q.strip())
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                status_code=503,
                code=PROVIDER_UNAVAILABLE,
                detail=f"MySQL unavailable: {exc}",
            ) from exc

    def get_job_summary(self, job_id: str) -> dict[str, Any]:
        """Return the persisted pipeline summary (matrix/findings/capsules)."""
        self.require_job(job_id)
        try:
            summary = self._store.get_job_summary(job_id)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                status_code=503,
                code=PROVIDER_UNAVAILABLE,
                detail=f"MySQL unavailable: {exc}",
            ) from exc
        return {"job_id": job_id, "summary": summary or {}}

    # ── Job lifecycle ─────────────────────────────────────────────

    def cancel_job(self, job_id: str, reason: str = "Cancelled by user") -> dict[str, Any]:
        """Cancel a QUEUED/RUNNING/FAILED job (CAS; terminal jobs immutable)."""
        try:
            job = self._store.get_job(job_id)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                status_code=503,
                code=PROVIDER_UNAVAILABLE,
                detail=f"MySQL unavailable: {exc}",
            ) from exc
        if job is None:
            raise ApiError(
                status_code=404,
                code=JOB_NOT_FOUND,
                detail=f"Job {job_id} not found",
            )
        current_status = str(job.get("status", ""))
        if current_status not in ("QUEUED", "RUNNING", "FAILED"):
            raise ApiError(
                status_code=409,
                code=STATE_CONFLICT,
                detail=f"Job {job_id} is {current_status} — cannot cancel a terminal job",
            )
        try:
            cancelled = self._store.transition_job_status(
                job_id, "CANCELLED", from_status=current_status,
                error_msg=reason,
            )
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                status_code=503,
                code=PROVIDER_UNAVAILABLE,
                detail=f"MySQL unavailable: {exc}",
            ) from exc
        if not cancelled:
            raise ApiError(
                status_code=409,
                code=STATE_CONFLICT,
                detail="Cancel failed (concurrent change)",
            )
        with contextlib.suppress(Exception):
            # Audit failure must not roll back a successful cancel.
            self._store.record_audit(
                action="job_cancelled", actor="api", job_id=job_id,
                from_status=current_status, to_status="CANCELLED",
            )
        return {"job_id": job_id, "status": "CANCELLED"}

    # ── Status constants (single source of truth) ────────────────

    @staticmethod
    def all_statuses() -> frozenset[str]:
        """All statuses the state machine can name."""
        return ALL_STATUSES


__all__ = ["VerificationApplicationService"]
