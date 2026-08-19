"""Job lifecycle API: create/query/cancel and the §14.3 progress SSE stream.

GET /jobs/{job_id}/progress → text/event-stream. Every progress event
carries a stable sequence number, event type, job id, stage, status,
percentage, summary and timestamp; Last-Event-ID reconnection resumes
after exactly the last received entry and replays the terminal event
idempotently. POST /jobs accepts only the documented allowlist fields —
arbitrary command/env/docker/output-path parameters are refused with
422 VALIDATION_FAILED.
"""
import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from api.auth import enforce_rate_limit, require_api_key
from api.errors import JOB_NOT_FOUND, PROVIDER_UNAVAILABLE, STATE_CONFLICT, ApiError
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

#: Documented POST /jobs payload fields (§14.3). Anything else is refused
#: with 422 VALIDATION_FAILED — the verification API must never become a
#: remote execution surface (no arbitrary command/env/docker/output-path).
JOB_CREATE_ALLOWLIST = frozenset(
    {"repo_path", "base_ref", "head_ref", "spec_path", "depth"}
)

#: Retained-history cap for one SSE replay (mirrors RedisStore.STREAM_MAXLEN;
#: kept local so the stream survives store monkeypatching in tests).
_SSE_HISTORY_CAP = 1000

#: The single event kind the VERIFY progress stream emits (§14.3).
_SSE_EVENT_TYPE = "progress"


def get_redis() -> RedisStore:
    global _redis
    if _redis is None:
        _redis = RedisStore()
    return _redis


class JobCreateRequest(BaseModel):
    """Job submission payload. Paths/refs are validated server-side.

    Strict allowlist (§14.3): any field outside JOB_CREATE_ALLOWLIST is
    rejected with 422 VALIDATION_FAILED naming the offending field, so
    arbitrary env/command/docker/output-path parameters never reach the
    worker.
    """

    repo_path: str = Field(min_length=1, max_length=1024)
    base_ref: str = Field(min_length=1, max_length=255)
    head_ref: str = Field(min_length=1, max_length=255)
    spec_path: str = Field(min_length=1, max_length=1024)
    depth: str = Field(default="FAST", pattern="^(FAST)$")

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_fields(cls, data: Any) -> Any:
        """Refuse any payload key outside the documented allowlist."""
        if isinstance(data, dict):
            unknown = sorted(
                str(key)
                for key in data
                if not isinstance(key, str) or key not in JOB_CREATE_ALLOWLIST
            )
            if unknown:
                raise ValueError(f"Unknown field(s): {', '.join(unknown)}")
        return data


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
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
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
            raise ApiError(
                status_code=404, code=JOB_NOT_FOUND, detail=f"Job {job_id} not found",
            )
        status = str(job.get("status", ""))
        if status not in ("QUEUED", "RUNNING", "WAITING_FOR_PROVIDER", "FAILED"):
            raise ApiError(
                status_code=409,
                code=STATE_CONFLICT,
                detail=f"Job {job_id} is {status} — cannot cancel a terminal job",
            )
        cancelled = store.transition_job_status(
            job_id, "CANCELLED", from_status=status, error_msg="Cancelled by user"
        )
        if not cancelled:
            raise ApiError(
                status_code=409,
                code=STATE_CONFLICT,
                detail="Cancel failed (concurrent change)",
            )
        store.record_audit(
            action="job_cancelled", actor="api", job_id=job_id,
            from_status=status, to_status="CANCELLED",
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"MySQL unavailable: {exc}",
        ) from exc
    return {"job_id": job_id, "status": "CANCELLED"}


@router.get("")
async def list_jobs(limit: int = 50) -> dict[str, Any]:
    """List the most recent verification jobs."""
    try:
        store = MySQLStore()
        rows = store.list_recent_jobs(limit)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"MySQL unavailable: {exc}",
        ) from exc
    return {"jobs": rows}


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Return one job's status from MySQL (the business source of truth)."""
    try:
        store = MySQLStore()
        job = store.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"MySQL unavailable: {exc}",
        ) from exc
    if job is None:
        raise ApiError(
            status_code=404, code=JOB_NOT_FOUND, detail=f"Job {job_id} not found",
        )
    return {"job": job}


@router.get("/{job_id}/summary")
async def get_job_summary(job_id: str) -> dict[str, Any]:
    """Return the persisted pipeline summary (matrix/findings/capsules)."""
    try:
        store = MySQLStore()
        job = store.get_job(job_id)
        if job is None:
            raise ApiError(
                status_code=404, code=JOB_NOT_FOUND, detail=f"Job {job_id} not found",
            )
        summary = store.get_job_summary(job_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=f"MySQL unavailable: {exc}",
        ) from exc
    return {"job_id": job_id, "summary": summary or {}}


class _DisconnectProbe(Protocol):
    """Minimal request surface the progress stream needs (testable)."""

    async def is_disconnected(self) -> bool: ...


class _ProgressReader(Protocol):
    """Minimal Redis progress-stream surface the SSE generator needs."""

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100,
    ) -> list[dict[str, Any]]: ...


def _progress_payload(job_id: str, seq: int, ev: dict[str, Any]) -> dict[str, Any]:
    """Shape one stream entry into the §14.3 progress event payload.

    seq is the entry's stable rank in the job's stream (monotonic across
    reconnections); stage/status/percentage/summary/ts mirror the worker's
    node/status/percent/message/at fields. Replays keep every field
    identical, so repeated consumption of the terminal event is idempotent.
    """
    return {
        "seq": seq,
        "job": job_id,
        "type": _SSE_EVENT_TYPE,
        "stage": str(ev.get("node") or ""),
        "status": str(ev.get("status") or ""),
        "percentage": float(ev.get("percent") or 0.0),
        "summary": str(ev.get("message") or ""),
        "ts": str(ev.get("at") or ""),
    }


async def _progress_stream(
    job_id: str,
    request: _DisconnectProbe,
    redis: _ProgressReader,
    last_event_id: str,
) -> AsyncGenerator[str, None]:
    """Yield §14.3 progress frames; resumes after Last-Event-ID.

    Frame format (the wire id stays the Redis stream entry id, unchanged):

        id: <stream-entry-id>
        event: progress
        data: {"seq": N, "job": "...", "type": "progress", "stage": "...",
               "status": "...", "percentage": F, "summary": "...", "ts": "..."}

    Every connection replays the retained history once so seq is the
    entry's stable rank in the stream rather than a per-connection counter.
    A client that reconnects with the last id it received resumes after
    exactly that entry (acknowledged entries are skipped and the terminal
    entry replays with an identical payload — repeat consumption is
    idempotent), while a stale/unknown id replays the full retained
    history instead of silently dropping events.
    """
    history = redis.xread_progress(job_id, from_id="0", count=_SSE_HISTORY_CAP)
    seq = 0
    last_emitted_id = "0"
    if last_event_id != "0":
        for idx, ev in enumerate(history):
            if str(ev.get("id")) == last_event_id:
                seq = idx + 1
                last_emitted_id = last_event_id
                break
    sent_ids: set[str] = set()
    replaying = True
    while True:
        if await request.is_disconnected():
            break
        if replaying:
            entries = history
        else:
            entries = redis.xread_progress(
                job_id, from_id=last_emitted_id, count=50,
            )
        for idx, ev in enumerate(entries):
            entry_id = str(ev.get("id"))
            if replaying:
                rank = idx + 1
                if rank <= seq:
                    continue
                seq = rank
            else:
                if entry_id in sent_ids:
                    continue
                seq += 1
            sent_ids.add(entry_id)
            last_emitted_id = entry_id
            payload = json.dumps(
                _progress_payload(job_id, seq, ev), ensure_ascii=False,
            )
            yield f"id: {entry_id}\n"
            yield f"event: {_SSE_EVENT_TYPE}\n"
            yield f"data: {payload}\n\n"
        replaying = False
        await asyncio.sleep(0.5)


@router.get("/{job_id}/progress")
async def job_progress(job_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint for job progress (§14.3).

    Reconnection: pass Last-Event-ID with the last received stream entry id
    and the stream resumes after exactly that entry. The terminal event is
    replayed with an identical seq/ts/payload for repeat consumption, so
    clients may safely re-process it. The stream stays open on live jobs
    and ends when the client disconnects.
    """
    last_event_id = request.headers.get("Last-Event-ID", "0")
    r = get_redis()
    return StreamingResponse(
        _progress_stream(job_id, request, r, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
