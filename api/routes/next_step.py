"""The next-step advice lane — the model reads this repository's real numbers
and proposes the next arc (nothing is judged, nothing is approved).

``POST /next-step/advice`` is PUBLIC, read-only and cacheable by fingerprint
(see ``api/next_step_advice.py`` for the packet + prompt rules).
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

router = APIRouter(prefix="/next-step", tags=["next-step"], dependencies=[Depends(enforce_rate_limit)])


class NextStepAdviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = Field(default="zh", max_length=5)


@router.post("/advice", status_code=200)
async def next_step_advice(payload: NextStepAdviceRequest) -> dict[str, Any]:
    """The model reads the ledger, chronicle and world book, and proposes
    the next arc — without ruling on anything."""
    locale = "en" if payload.locale.strip().lower() == "en" else "zh"
    from api.next_step_advice import (
        NextStepAdviceError,
        fingerprint,
        generate_next_step_advice,
        next_step_redis,
    )

    cache_key = f"next-step-advice:{fingerprint(locale)[:16]}"
    redis = next_step_redis()
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
        result = await generate_next_step_advice(locale)
    except NextStepAdviceError as exc:
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
                cache_key, body, ttl=int_env("NEXT_STEP_ADVICE_TTL_SECONDS", 86_400),
            )
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.info(
                "next-step-advice cache write failed (continuing uncached): %s: %s",
                type(exc).__name__, exc,
            )
    return body
