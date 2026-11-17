"""The Observatory's public advice lane — everyone may ask; nobody is judged.

``POST /observe/advice`` is a PUBLIC endpoint. It answers one question —
"what does the model read out of this panel" — for a panel that contains no
real person: a seeded 240-member synthetic calibration cohort plus whatever
this browser already stored locally. The server computes the packet itself
(``api/synthetic_cohort.py``); clients send only a language preference,
never numbers.

No API key, no RBAC cell, no session. Protection is by construction:

* the packet is identical for every caller, so the Redis fingerprint cache
  turns the common case into a constant-time hit — model spend is one call
  per (locale × TTL window), not per visitor;
* the per-IP-anonymous rate limit (shared ``specproof:rl:anonymous`` bucket,
  fixed window, fail-open) bounds the cache-miss path;
* on any model failure the answer is one honest 503 — never a fabricated
  paragraph and never a verdict of any kind;
* tenant-mode middleware (``api/middleware.py``) lists ``/observe/`` in the
  open prefixes, exactly like ``/health`` — read it next to ``/auth/oidc/``.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.auth import enforce_rate_limit
from api.errors import PROVIDER_UNAVAILABLE, ApiError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observe", tags=["observe"], dependencies=[Depends(enforce_rate_limit)])


class ObserveAdviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = Field(default="zh", max_length=5)


@router.post("/advice", status_code=200)
async def observe_advice(payload: ObserveAdviceRequest) -> dict[str, Any]:
    """The model reads the Observatory's aggregates and says what it sees.

    Public, read-only, cached by fingerprint (a packet is five seconds of
    deterministic arithmetic) — and never a verdict of any kind.
    """
    locale = "en" if payload.locale.strip().lower() == "en" else "zh"
    from api.observe_advice import (
        ObserveAdviceUnavailable,
        fingerprint,
        generate_observe_advice,
        observe_redis,
    )

    cache_key = f"observe-advice:{fingerprint(locale)[:16]}"
    redis = observe_redis()
    cached: dict[str, Any] | None = None
    if redis is not None:
        try:
            cached = redis.get_cached_llm_response(cache_key)
        except Exception:  # noqa: BLE001 - cache read failure is not a verdict
            cached = None
    if cached is not None:
        cached = dict(cached)
        cached["cached"] = True
        return cached

    started = time.perf_counter()
    try:
        result = await generate_observe_advice(locale)
    except ObserveAdviceUnavailable as exc:
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE, detail=str(exc),
        ) from exc

    body: dict[str, Any] = {
        "advice": result["advice"],
        "model": result.get("model"),
        "model_latency_ms": result.get("model_latency_ms")
        or round((time.perf_counter() - started) * 1000),
        "evidence_packet_chars": result["evidence_packet_chars"],
        "usage": result.get("usage"),
        "cached": False,
    }
    if redis is not None:
        try:
            from storage.env_config import int_env

            redis.cache_llm_response(
                cache_key, body, ttl=int_env("OBSERVE_ADVICE_TTL_SECONDS", 86_400),
            )
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.info(
                "observe-advice cache write failed (continuing uncached): %s: %s",
                type(exc).__name__, exc,
            )
    return body
