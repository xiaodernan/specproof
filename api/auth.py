"""API authentication and rate limiting (P0-A2).

Fail-closed authentication: when SPECPROOF_API_KEY is not configured the
API refuses job operations with 503 — an unauthenticated task queue is an
SSRF/resource-abuse hole, so "no key configured" must never mean "open".

Rate limiting is abuse protection (fixed-window counter in Redis), NOT a
security boundary: when Redis is unavailable the request is allowed and the
degradation is logged (availability first), while authentication always
fails closed.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _configured_key() -> str:
    return os.getenv("SPECPROOF_API_KEY", "").strip()


def require_api_key(request: Request) -> None:
    """Reject requests without a valid API key (constant-time comparison)."""
    expected = _configured_key()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "API key not configured: set SPECPROOF_API_KEY and restart. "
                "The API refuses to accept jobs without authentication."
            ),
        )
    supplied = request.headers.get("X-API-Key", "")
    if not supplied:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            supplied = auth_header[len("Bearer "):]
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def enforce_rate_limit(request: Request) -> None:
    """Fixed-window rate limit per API key (Redis-backed, fail-open)."""
    key = request.headers.get("X-API-Key", "") or "anonymous"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    window = int(time.time()) // 60
    redis_key = f"specproof:rl:{digest}:{window}"
    limit = int(os.getenv("SPECPROOF_RATE_LIMIT_PER_MIN", "60"))

    try:
        from storage.redis import RedisStore

        store = RedisStore()
        count = store.client.incr(redis_key)
        if count == 1:
            store.client.expire(redis_key, 90)
        if int(count) > limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit} requests/min per key)",
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — availability first, log the gap
        logger.warning("Rate limiter unavailable, allowing request: %s", exc)
