"""FastAPI server for SpecProof.

Provides:
  - POST /jobs                       create job + outbox event (one transaction)
  - GET  /jobs                       list recent jobs
  - GET  /jobs/{job_id}              job status (MySQL = source of truth)
  - GET  /jobs/{job_id}/summary      persisted pipeline summary (dashboard)
  - GET  /jobs/{job_id}/progress     SSE with Last-Event-ID
  - GET  /dashboard                  web dashboard (static, API-key protected)
  - GET  /                           React SPA (apps/web/dist) or dashboard redirect
  - GET  /api/v1/*                   read-only web UI APIs (dashboard/stages/
                                      findings/certificate/capsule/contracts/
                                      eval/health; all key-protected)
  - GET  /metrics                    Prometheus metrics
  - GET  /health                     readiness probe
"""

import logging
import sys
from pathlib import Path

# Ensure project root on path (enables python -m api.server from a checkout)
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import Any  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api.routes.jobs import router as jobs_router  # noqa: E402
from api.routes.web import router as web_router  # noqa: E402
from api.routes.webhooks import router as webhooks_router  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SpecProof Phase 1",
    version="0.1.0",
    description="Reliable Verification Job API",
)

import os  # noqa: E402

# CORS whitelist from configuration; never "*" in production.
_cors_origins = os.getenv(
    "SPECPROOF_CORS_ORIGINS", "http://localhost:3000,http://localhost:8000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(webhooks_router)
app.include_router(web_router)

# P0-A4: refuse to start in production with default credentials.
from storage.config_guard import enforce_production_config  # noqa: E402

enforce_production_config()

# C1: OTel instrumentation + structured JSON logs (degrade to NoOp without
# the SDK; SPECPROOF_OTEL_ENABLED=1 turns tracing on).
from observability.logging import configure_logging  # noqa: E402
from observability.middleware import add_trace_middleware  # noqa: E402

configure_logging()
add_trace_middleware(app)


@app.middleware("http")
async def request_metrics(request: Request, call_next: Any) -> Any:
    """Count every request by route (observability baseline)."""
    from api.metrics import incr

    incr("http_requests_total")
    try:
        response = await call_next(request)
    except Exception:
        incr("http_requests_failed_total")
        raise
    if response.status_code >= 500:
        incr("http_responses_5xx_total")
    return response


# ── Web dashboard (static; the JSON APIs it calls are key-protected) ──
_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.exists():
    app.mount("/dashboard/static", StaticFiles(directory=str(_static_dir)), name="dashboard-static")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_index() -> RedirectResponse:
        return RedirectResponse(url="/dashboard/static/index.html")


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Any:
    """Prometheus text exposition (scrape endpoint for the OTel/Prom stack)."""
    from fastapi.responses import PlainTextResponse

    from api.metrics import render_text

    return PlainTextResponse(render_text())


@app.get("/health")
async def health() -> dict[str, str | bool]:
    from storage.redis import RedisStore
    r = RedisStore()
    redis_ok = r.is_ready()
    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": redis_ok,
    }


# ── React SPA (apps/web/dist preferred; static dashboard as fallback) ──
# The SPA is served without a key (its JSON APIs are key-protected, same as
# the legacy static dashboard). When apps/web/dist does not exist (no npm
# build yet), the legacy /dashboard static page remains the only UI.
# This block is registered LAST so the catch-all never shadows real routes.
_web_dist = Path(__file__).resolve().parents[1] / "apps" / "web" / "dist"
_SPA_RESERVED_PREFIXES = (
    "api/",
    "jobs",
    "metrics",
    "health",
    "webhooks",
    "dashboard",
    "docs",
    "redoc",
    "openapi.json",
)

if _web_dist.is_dir() and (_web_dist / "index.html").is_file():
    if (_web_dist / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_web_dist / "assets")),
            name="spa-assets",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """SPA deep-link fallback: unknown non-API paths serve index.html."""
        if full_path.startswith(_SPA_RESERVED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_web_dist / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(_web_dist.resolve())
        ):
            return FileResponse(str(candidate))
        return FileResponse(str(_web_dist / "index.html"))


def main() -> None:
    import uvicorn

    # Containerized deployment listens on all interfaces; authentication and
    # rate limiting are enforced at the app layer, so this is intentional.
    host = os.getenv("SPECPROOF_API_HOST", "0.0.0.0")  # nosec
    uvicorn.run(app, host=host, port=8000, log_level="info")


if __name__ == "__main__":
    main()
