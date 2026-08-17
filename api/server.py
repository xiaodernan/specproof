"""FastAPI server for SpecProof Phase 1.

Provides:
  - GET  /jobs/{job_id}/progress  (SSE with Last-Event-ID)
  - GET  /health                   (readiness probe)
"""

import logging
import sys
from pathlib import Path

# Ensure project root on path
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.jobs import router as jobs_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SpecProof Phase 1",
    version="0.1.0",
    description="Reliable Verification Job API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(jobs_router)


@app.get("/health")
async def health():
    from storage.redis import RedisStore
    r = RedisStore()
    redis_ok = r.is_ready()
    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": redis_ok,
    }


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
