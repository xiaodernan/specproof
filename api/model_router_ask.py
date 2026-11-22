"""The model-driven routing lane — the reader's question is routed by the model
itself, and the chosen lane writes the answer. The product face of the
``model_router_graph`` StateGraph (#1638).

WHY THIS EXISTS. The StateGraph was real but only reachable from a CLI and a
showcase card — a capability the user could not call. This module is the public
async face of the SAME graph semantics: the model's structured output picks one
of three lanes (``evidence`` / ``worldbook`` / ``nextstep``), and that label
drives which content node runs. Nothing here is a witness: an API call always
talks to the model.

HONESTY / CACHE CONTRACT (shared with the ask-the-book lane):
* one frozen, cacheable ``codex_first`` prefix rides in on every call — the
  expensive system prompt is byte-identical across requests and sessions;
* a STICKY ``prompt_cache_key`` (``specproof-model-router``) — the same key for
  the same lane on every call, the way Codex keeps its prefix warm. A per-
  request random key is what fragments the cache across parallel sessions;
* two model calls at most (route, then content) with the SAME sticky key so the
  prefix is only ever charged once;
* the route is constrained to an allowlist — a hallucinated label cannot leave
  the graph. The content is checked for verdict words — this lane never grades
  an exhibit, it only explains routes and writes lane content;
* any provider failure is one honest error, never a fabricated route/answer.

The graph module is the single source of truth for the messages, the allowlist,
the parser, the verdict guard and the cache-token reader. This module reuses
them instead of restating them.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any, Callable

from providers.base import LLMResponse

from agent.graphs import model_router_graph as graph

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 480
LLM_TIMEOUT_SECONDS = 120.0
STICKY_CACHE_KEY = "specproof-model-router"


class _SingleFlight:
    """Coalesce concurrent misses on the same key into ONE loader call.

    The owner's worry is real: parallel sessions striking a cold fingerprint
    all miss the Redis cache at once, so N sessions make N model calls and the
    cache 'looks' cold. Within one process, this merges them: the first caller
    becomes the leader and runs the loader; the rest await the same future.
    Cross-process coalescing is left to the Redis fingerprint cache itself.

    Pure asyncio — no threads, no locks, nothing that blocks the event loop.
    """

    def __init__(self) -> None:
        self._futures: dict[str, asyncio.Future] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def run(self, key: str, loader) -> Any:  # noqa: ANN001
        loop = asyncio.get_running_loop()
        # A future belongs to the loop that created it. TestClients and some
        # ASGI hosts run different requests on different loops; a future from
        # another loop cannot be awaited here, so treat it as no flight.
        if self._loop is not loop:
            self._futures.clear()
            self._loop = loop
        inflight = self._futures.get(key)
        if inflight is not None and not inflight.done():
            return await asyncio.shield(inflight)
        future: asyncio.Future = loop.create_future()
        self._futures[key] = future
        try:
            value = await loader()
        except BaseException as exc:  # noqa: BLE001 - every waiter shares the honest failure
            if not future.done():
                future.set_exception(exc)
                # Mark the exception retrieved on the leader's own behalf: if
                # nobody joined the flight, asyncio would otherwise warn about
                # an unconsumed future exception at teardown. Waiters still get
                # the real exception when they await the shared future.
                future.exception()
            raise
        else:
            if not future.done():
                future.set_result(value)
            return value
        finally:
            # Drop only our own entry; a later leader may already have replaced it.
            if self._futures.get(key) is future:
                self._futures.pop(key, None)


_answer_singleflight = _SingleFlight()


class ModelRouterAskError(RuntimeError):
    """An honest failure of the routing lane (never a fabricated route)."""


def _sanitize(text: str) -> str:
    cleaned = "".join(ch for ch in (text or "") if ch.isprintable())
    return " ".join(cleaned.split())[:MAX_QUESTION_CHARS]


def fingerprint(locale: str, question: str) -> str:
    import hashlib

    return hashlib.sha256(
        f"{locale}|{_sanitize(question)}".encode("utf-8")
    ).hexdigest()


def _locale(value: str) -> str:
    return "en" if (value or "").strip().lower() == "en" else "zh"


def _content_prompt(lane: str, locale: str, question: str) -> str:
    if locale == "en":
        return f"Answer on the {lane} lane, in English, plainly and briefly: {question}"
    return f"在{lane}车道上，用中文简明回答：{question}"


#: Only these are additive counters. Derived fields (``cached_tokens_seen``,
#: ``cache_hit_ratio``) and nested dicts must not be summed — summing a derived
#: cache ratio twice is exactly how a healthy cache 'looks' lost.
_ADDITIVE_TOKEN_KEYS = (
    "prompt_tokens", "completion_tokens", "total_tokens",
    "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
)


def _merge_usage(*usages: dict[str, Any] | None) -> dict[str, Any]:
    """Sum the token counters across the two calls; keep cache hits visible."""
    merged: dict[str, Any] = {}
    for usage in usages:
        for k, v in (usage or {}).items():
            if k in _ADDITIVE_TOKEN_KEYS and isinstance(v, (int, float)):
                merged[k] = merged.get(k, 0) + v
            elif k not in merged and k not in ("prompt_tokens_details",):
                merged[k] = v
            elif k == "prompt_tokens_details" and isinstance(v, dict):
                details = dict(merged.get(k) or {})
                for dk, dv in v.items():
                    if isinstance(dv, (int, float)):
                        details[dk] = details.get(dk, 0) + dv
                merged[k] = details
    # Normalize the raw OpenAI nested shape into the canonical counter so a
    # mixed-shape pair (one call normalized, one raw) still sums to one truth.
    details = merged.get("prompt_tokens_details") or {}
    nested_hits = 0
    if isinstance(details, dict):
        try:
            nested_hits = int(details.get("cached_tokens") or 0)
        except (ValueError, TypeError):
            nested_hits = 0
    if nested_hits:
        merged["prompt_cache_hit_tokens"] = merged.get("prompt_cache_hit_tokens", 0) + nested_hits
    cached = graph.cached_tokens_of(merged)
    merged["cached_tokens_seen"] = cached
    total_prompt = 0
    for usage in usages:
        try:
            total_prompt += int((usage or {}).get("prompt_tokens") or 0)
        except (ValueError, TypeError):
            continue
    if total_prompt:
        merged["cache_hit_ratio"] = round(cached / total_prompt, 4)
    return merged


async def run_model_router(
    question: str,
    locale: str = "zh",
    *,
    provider_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Route the question through the model, then answer on the chosen lane.

    Two model calls at most (both under the SAME sticky cache key). The route
    decides the branch exactly as ``add_conditional_edges`` does in the graph.
    Raise ModelRouterAskError only on honest provider failures.
    """
    from providers.openai_compatible import OpenAICompatibleProvider

    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    clean = _sanitize(question)
    if not clean:
        raise ValueError("empty question")
    lang = _locale(locale)
    started = time.perf_counter()
    provider: Any = None
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=1)

        # Node 1: route. The model's structured output is the conditional edge.
        route_resp: LLMResponse = await asyncio.wait_for(
            provider.chat(
                graph._router_messages(lang, clean),
                response_format={"type": "json_object"},
                opts={"prompt_cache_key": STICKY_CACHE_KEY},
            ),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
        route, rationale = graph._parse_route(route_resp.content or "")
        if not route:  # hallucinated / unparseable → ROUTE-DRIFT, no content call
            return {
                "route": "",
                "route_source": "model",
                "route_drift": True,
                "rationale": rationale,
                "content": "",
                "verdict": "ROUTE-DRIFT",
                "model": route_resp.model or None,
                "usage": _merge_usage(route_resp.usage),
                "question_chars": len(clean),
                "locale": lang,
            }

        # Node 2: the chosen branch writes content (the conditional edge's target).
        from api.system_codex import codex_first
        from providers.base import LLMMessage

        content_resp: LLMResponse = await asyncio.wait_for(
            provider.chat(
                codex_first(
                    [LLMMessage(role="user", content=_content_prompt(route, lang, clean))],
                    lang,
                ),
                opts={"prompt_cache_key": STICKY_CACHE_KEY},
            ),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
        content = (content_resp.content or "").strip()[:1200]

        # Node 3: verdict guard — content may never rule on an exhibit.
        verdict = "HELD"
        detail = "route allowlisted, content verdict-free"
        if graph._VERDICT_WORDS.search(content):
            content = ""
            verdict = "VERDICT-LEAK"
            detail = "model claimed a verdict — refused; this lane never grades an exhibit"
        elif not content:
            verdict = "MODEL-FAILURE"
            detail = "model returned empty content"

        return {
            "route": route,
            "route_source": "model",
            "route_drift": False,
            "rationale": rationale,
            "content": content,
            "verdict": verdict,
            "detail": detail,
            "model": content_resp.model or route_resp.model or None,
            "model_latency_ms": round((time.perf_counter() - started) * 1000),
            "usage": _merge_usage(route_resp.usage, content_resp.usage),
            "question_chars": len(clean),
            "locale": lang,
        }
    except Exception as exc:  # noqa: BLE001 - one honest error, never a fabrication
        logger.info("model-router failure: %s", type(exc).__name__)
        raise ModelRouterAskError(
            "the model is unavailable right now — no route was fabricated; try again later."
            if lang == "en"
            else "模型暂时不可用——没有编造任何选路；稍后再试。"
        ) from exc
    finally:
        if provider is not None:
            with contextlib.suppress(Exception):
                await provider.close()
