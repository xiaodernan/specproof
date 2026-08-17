"""Job progress SSE endpoint.

GET /jobs/{job_id}/progress → text/event-stream
Supports Last-Event-ID for reconnection catch-up.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from storage.redis import RedisStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

_redis: RedisStore | None = None


def get_redis() -> RedisStore:
    global _redis
    if _redis is None:
        _redis = RedisStore()
    return _redis


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
                yield f"event: progress\n"
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
