"""Job progress SSE endpoint.

GET /jobs/{job_id}/progress → text/event-stream
Supports Last-Event-ID for reconnection catch-up.
"""
import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import enforce_rate_limit, require_api_key
from storage.mysql import MySQLStore
from storage.redis import RedisStore

logger = logging.getLogger(__name__)

# P0-A2: every job operation requires a valid API key and is rate limited.
# /health stays open (liveness), everything else fails closed.
router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)

_redis: RedisStore | None = None


def get_redis() -> RedisStore:
    global _redis
    if _redis is None:
        _redis = RedisStore()
    return _redis


class JobCreateRequest(BaseModel):
    """Job submission payload. Paths/refs are validated server-side."""

    repo_path: str = Field(min_length=1, max_length=1024)
    base_ref: str = Field(min_length=1, max_length=255)
    head_ref: str = Field(min_length=1, max_length=255)
    spec_path: str = Field(min_length=1, max_length=1024)
    depth: str = Field(default="FAST", pattern="^(FAST)$")


@router.post("", status_code=202)
async def create_job(payload: JobCreateRequest) -> dict[str, Any]:
    """Create a verification job and its Outbox event in ONE MySQL transaction.

    The job row and the outbox row commit together: if the API crashes before
    responding, the relay still publishes the event (at-least-once). The
    consumer is idempotent, so a duplicate delivery cannot double-process.

    Returns 202 with job_id. A real 503 when MySQL is unreachable — the API
    never pretends a job was accepted when nothing was persisted.
    """
    job = {
        "id": str(uuid.uuid4()),
        "repo_path": payload.repo_path,
        "base_ref": payload.base_ref,
        "head_ref": payload.head_ref,
        "spec_path": payload.spec_path,
        "depth": payload.depth,
    }
    try:
        store = MySQLStore()
        job_id = store.create_job_with_outbox(job)
    except Exception as exc:  # noqa: BLE001 — MySQL down / schema missing
        logger.exception("Failed to persist job via outbox")
        raise HTTPException(
            status_code=503,
            detail=f"Job NOT accepted — persistence failed: {exc}",
        ) from exc
    return {"job_id": job_id, "status": "QUEUED"}


@router.post("/{job_id}/cancel", status_code=202)
async def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel a QUEUED/RUNNING job (CAS; terminal jobs are immutable)."""
    try:
        store = MySQLStore()
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        status = str(job.get("status", ""))
        if status not in ("QUEUED", "RUNNING", "WAITING_FOR_PROVIDER", "FAILED"):
            raise HTTPException(
                status_code=409,
                detail=f"Job {job_id} is {status} — cannot cancel a terminal job",
            )
        cancelled = store.transition_job_status(
            job_id, "CANCELLED", from_status=status, error_msg="Cancelled by user"
        )
        if not cancelled:
            raise HTTPException(status_code=409, detail="Cancel failed (concurrent change)")
        store.record_audit(
            action="job_cancelled", actor="api", job_id=job_id,
            from_status=status, to_status="CANCELLED",
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MySQL unavailable: {exc}") from exc
    return {"job_id": job_id, "status": "CANCELLED"}


@router.get("")
async def list_jobs(limit: int = 50) -> dict[str, Any]:
    """List the most recent verification jobs."""
    try:
        store = MySQLStore()
        rows = store.list_recent_jobs(limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MySQL unavailable: {exc}") from exc
    return {"jobs": rows}


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Return one job's status from MySQL (the business source of truth)."""
    try:
        store = MySQLStore()
        job = store.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MySQL unavailable: {exc}") from exc
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {"job": job}


@router.get("/{job_id}/summary")
async def get_job_summary(job_id: str) -> dict[str, Any]:
    """Return the persisted pipeline summary (matrix/findings/capsules)."""
    try:
        store = MySQLStore()
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        summary = store.get_job_summary(job_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MySQL unavailable: {exc}") from exc
    return {"job_id": job_id, "summary": summary or {}}


@router.get("/{job_id}/progress")
async def job_progress(job_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint for job progress. Supports reconnection via Last-Event-ID.

    Event format:
        id: <stream-entry-id>
        event: progress
        data: {"node": "...", "status": "...", "percent": N, "message": "..."}

    The client disconnects, then reconnects with Last-Event-ID header set to
    the last received event id. The server resumes from that position.
    """
    last_event_id = request.headers.get("Last-Event-ID", "0")
    r = get_redis()

    async def event_generator() -> AsyncGenerator[str, None]:
        from_id = last_event_id
        sent_ids: set[str] = set()

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            # Fetch new events
            events = r.xread_progress(job_id, from_id=from_id, count=50)
            for ev in events:
                if ev["id"] in sent_ids:
                    continue
                sent_ids.add(ev["id"])

                payload = json.dumps({
                    "node": ev["node"],
                    "status": ev["status"],
                    "percent": ev["percent"],
                    "message": ev["message"],
                }, ensure_ascii=False)
                yield f"id: {ev['id']}\n"
                yield "event: progress\n"
                yield f"data: {payload}\n\n"
                from_id = ev["id"]

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
