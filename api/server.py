"""API server — FastAPI with SSE progress endpoint (P1.4).

Start: uvicorn api.server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from storage.mysql import JobNotFoundError, MySQLStore
from storage.redis import RedisStore

logger = logging.getLogger(__name__)

app = FastAPI(title="SpecProof P1 API", version="0.1.0")

_mysql: MySQLStore | None = None
_redis: RedisStore | None = None


def get_mysql() -> MySQLStore:
    global _mysql
    if _mysql is None:
        _mysql = MySQLStore()
        _mysql.ensure_tables()
    return _mysql


def get_redis() -> RedisStore:
    global _redis
    if _redis is None:
        _redis = RedisStore()
    return _redis


@app.on_event("startup")
async def startup() -> None:
    get_mysql()
    get_redis()


@app.get("/health")
async def health() -> dict[str, Any]:
    mysql_ok = get_mysql().is_ready()
    redis_ok = get_redis().is_ready()
    return {
        "status": "ok" if (mysql_ok and redis_ok) else "degraded",
        "mysql": mysql_ok,
        "redis": redis_ok,
    }


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    store = get_mysql()
    job = store.get_job(job_id)
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found")
    return JSONResponse(content={
        "job_id": job.get("id"),
        "status": job.get("status"),
        "version": job.get("version"),
        "repo_path": job.get("repo_path"),
        "base_ref": job.get("base_ref"),
        "head_ref": job.get("head_ref"),
        "retry_count": job.get("retry_count"),
        "last_error": job.get("last_error"),
        "created_at": str(job.get("created_at", "")),
        "updated_at": str(job.get("updated_at", "")),
        "started_at": str(job.get("started_at", "")),
        "completed_at": str(job.get("completed_at", "")),
    })


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint for job progress. Supports Last-Event-ID resumption."""
    redis_store = get_redis()
    last_event_id = request.headers.get("Last-Event-ID", "0")

    async def stream() -> Any:
        from_id = last_event_id
        # First send any missed events
        if from_id != "$":
            entries = redis_store.xread_progress(job_id, from_id=from_id)
            for entry in entries:
                eid = entry.get("id", "")
                yield f"id: {eid}\n"
                yield f"data: {entry}\n\n"

        # Then stream new events via polling (no blocking XREAD in async)
        while True:
            if await request.is_disconnected():
                break
            entries = redis_store.xread_progress(job_id, from_id=from_id)
            for entry in entries:
                eid = entry.get("id", "")
                yield f"id: {eid}\n"
                yield f"data: {entry}\n\n"
                from_id = eid
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.exception_handler(JobNotFoundError)
async def job_not_found_handler(request: Request, exc: JobNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})
