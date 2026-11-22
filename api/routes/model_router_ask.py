"""The model-driven routing lane — public, cheap, honest.

``POST /route/ask`` is the product face of the #1638 StateGraph: the model
chooses one of three lanes and the chosen lane writes the answer. No API key,
no session. Protection mirrors ``/worldbook/ask``:

* sanitized question + locale fingerprint → Redis cache (repeated questions
  re-read a warm answer, never a fresh two-call model round-trip);
* the shared anonymous rate limit bounds the cache-miss path;
* both model calls ride a STICKY ``prompt_cache_key`` under one frozen codex
  prefix — parallel sessions share the same cache entry instead of fragmenting it;
* on any failure one honest 503, never a fabricated route.
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

router = APIRouter(
    prefix="/route",
    tags=["model-router"],
    dependencies=[Depends(enforce_rate_limit)],
)

_MAX_QUESTION_CHARS = 480


class RouteAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=_MAX_QUESTION_CHARS)
    locale: str = Field(default="zh", max_length=5)


def _redis() -> Any | None:
    from api.worldbook_ask import ask_redis

    return ask_redis()


@router.post("/ask", status_code=200)
async def route_ask(payload: RouteAskRequest) -> dict[str, Any]:
    from api.model_router_ask import (
        ModelRouterAskError,
        fingerprint,
        run_model_router,
    )

    locale = "en" if payload.locale.strip().lower() == "en" else "zh"
    cache_key = f"model-router-ask:{fingerprint(locale, payload.question)[:24]}"

    redis = _redis()
    if redis is not None:
        try:
            cached = redis.get_cached_llm_response(cache_key)
        except Exception:  # noqa: BLE001 - cache read failure is not a route
            cached = None
        if cached is not None:
            body = dict(cached)
            body["cached"] = True
            return body

    started = time.perf_counter()
    try:
        result = await run_model_router(payload.question, locale)
    except ValueError as exc:
        raise ApiError(status_code=400, code="INVALID_ARGUMENT", detail=str(exc)) from exc
    except ModelRouterAskError as exc:
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE, detail=str(exc),
        ) from exc

    result["cached"] = False
    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    if redis is not None:
        try:
            from storage.env_config import int_env

            redis.cache_llm_response(
                cache_key, result,
                ttl=int_env("MODEL_ROUTER_ASK_TTL_SECONDS", 604_800),
            )
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.info(
                "model-router cache write failed (continuing uncached): %s: %s",
                type(exc).__name__, exc,
            )
    return result
