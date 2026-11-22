"""The worldbook ask lane — anyone may ask the book; nothing answers but the book.

``POST /worldbook/ask`` is a PUBLIC endpoint. The world book is the repo's
fiction-and-fact: the bible (``docs/world/SPECROOF_WORLD*.md``) plus the iron
lexicon. The model has read the book once — it rides in as the shared codex
prefix (byte-frozen, cacheable, 94% hit rate on a warm pair); the question is
the only client input; the answer is what the book itself would say — no
verdict is ever minted, and the answer is never dressed as fact when the
book does not carry it.

No API key, no RBAC cell, no session. Protection is by construction:

* the question is sanitized (printable only, ~480 chars) and the fingerprint
  (question × locale) feeds a Redis cache — repeated similar questions
  re-read the warm prefix, never a fresh bible read;
* the per-IP-anonymous rate limit (shared ``specproof:rl:anonymous`` bucket,
  fixed window, fail-open) bounds the cache-miss path;
* on any model failure the answer is one honest 503 — never a fabricated
  paragraph, never a verdict;
* tenant-mode middleware (``api/middleware.py``) lists ``/worldbook/`` in
  the open prefixes, exactly like ``/observe/`` and ``/health``.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.auth import enforce_rate_limit
from api.errors import PROVIDER_UNAVAILABLE, ApiError
from api.singleflight import SingleFlight
from api.worldbook_ask import MAX_QUESTION_CHARS

logger = logging.getLogger(__name__)

# Its own flight registry: the world-book prefix keeps in-flight keys apart
# from the model-router lane, so a question shared by both cannot cross-coalesce.
_book_singleflight = SingleFlight()

router = APIRouter(prefix="/worldbook", tags=["worldbook"], dependencies=[Depends(enforce_rate_limit)])


class WorldbookAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    locale: str = Field(default="zh", max_length=5)


@router.post("/ask", status_code=200)
async def worldbook_ask(payload: WorldbookAskRequest) -> dict[str, Any]:
    """Ask the book through the model. Public, cheap, honest — never a verdict."""
    locale = "en" if payload.locale.strip().lower() == "en" else "zh"
    from api.worldbook_ask import (
        WorldbookAskError,
        ask_redis,
        fingerprint,
        generate_ask_answer,
    )

    cache_key = f"worldbook-ask:{fingerprint(locale, payload.question)[:24]}"
    redis = ask_redis()
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

    async def load_once() -> dict[str, Any]:
        # A leader may have filled the cache while we waited for the flight.
        if redis is not None:
            try:
                raced = redis.get_cached_llm_response(cache_key)
            except Exception:  # noqa: BLE001
                raced = None
            if raced is not None:
                body = dict(raced)
                body["cached"] = True
                return body

        started = time.perf_counter()
        try:
            result = await generate_ask_answer(payload.question, locale)
        except ValueError as exc:
            raise ApiError(status_code=400, code="INVALID_ARGUMENT", detail=str(exc)) from exc
        except WorldbookAskError as exc:
            raise ApiError(
                status_code=503, code=PROVIDER_UNAVAILABLE, detail=str(exc),
            ) from exc

        body: dict[str, Any] = {
            "answer": result["answer"],
            "model": result.get("model"),
            "model_latency_ms": result.get("model_latency_ms")
            or round((time.perf_counter() - started) * 1000),
            "usage": result.get("usage"),
            "question_chars": result.get("question_chars"),
            "cached": False,
        }
        if redis is not None:
            try:
                from storage.env_config import int_env

                redis.cache_llm_response(
                    cache_key, body, ttl=int_env("WORLDBOOK_ASK_TTL_SECONDS", 604_800),
                )
            except Exception as exc:  # noqa: BLE001 - persistence is best-effort
                logger.info(
                    "worldbook-ask cache write failed (continuing uncached): %s: %s",
                    type(exc).__name__, exc,
                )
        return body

    # Concurrent cold misses on this fingerprint share one model call.
    return await _book_singleflight.run(cache_key, load_once)
