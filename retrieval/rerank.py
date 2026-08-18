"""Rerank layer (RAG 2.0, 卷IV 4.2/4.3) — three honest tiers.

Tier 1 (cross-encoder): RERANK_MODEL names a sentence-transformers
cross-encoder. sentence-transformers is an OPTIONAL dependency (not in
pyproject.toml) — an import/load failure means this tier is unavailable,
never a crash.

Tier 2 (LLM listwise): when the LLM gateway is configured, one JSON
listwise call under an input budget (candidate count × content chars).
Invalid or missing output falls back to tier 3.

Tier 3 (off): original order preserved, honestly annotated
(mode="off" + reason). 卷IV 4.3: 重排模型缺失 → rerank=off 保序.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
from dataclasses import dataclass
from typing import Any

_DEFAULT_MAX_CANDIDATES = 20
_DEFAULT_CONTENT_CHARS = 200
_cross_encoder_cache: dict[str, Any] = {}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


@dataclass
class RerankResult:
    """Outcome of one rerank call: mode + a permutation of the candidates."""

    mode: str  # "cross_encoder" | "llm" | "off"
    order: list[int]
    scores: list[float] | None = None
    reason: str | None = None


def _load_cross_encoder(model_name: str) -> Any | None:
    """Load a sentence-transformers CrossEncoder (cached); None when unavailable."""
    cached = _cross_encoder_cache.get(model_name)
    if cached is not None:
        return cached
    try:
        from sentence_transformers import CrossEncoder

        encoder = CrossEncoder(model_name)
    except Exception:  # noqa: BLE001 — optional dependency, honest degradation
        return None
    _cross_encoder_cache[model_name] = encoder
    return encoder


def _candidate_text(candidate: dict[str, Any], content_chars: int) -> str:
    symbol = str(candidate.get("symbol", "") or "")
    content = str(candidate.get("content", "") or "")[:content_chars]
    return (symbol + ": " + content) if symbol else content


def _llm_provider() -> Any | None:
    """LLM gateway provider from env; None when not configured (mirrors nodes)."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:  # noqa: BLE001 — provider stack optional for rerank
        return None


def _run_async(coro: Any) -> Any:
    """Run an async provider call from a sync context (nodes are sync)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=90)


def _llm_order(provider: Any, query: str, texts: list[str]) -> list[int] | None:
    """Ask the LLM for a best-first permutation of candidate indices.

    Returns None on any failure (never a partial ranking): invalid JSON,
    wrong shape, or a non-permutation all fall back to the original order.
    """
    from providers.base import LLMMessage
    from providers.redaction import redact_text

    safe_query, _scrubbed = redact_text(query[:2000])
    listing = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
    prompt = (
        "You are a retrieval reranker. Rank the following code candidates by "
        "relevance to the query. Reply with ONLY a JSON array of candidate "
        "indices, best first, covering every index exactly once.\n"
        "Query: " + safe_query + "\nCandidates:\n" + listing
    )
    try:
        response = _run_async(
            provider.chat(
                messages=[LLMMessage(role="user", content=prompt)], timeout=60.0
            )
        )
        content = response.content or ""
        start = content.find("[")
        end = content.rfind("]")
        if start < 0 or end <= start:
            return None
        parsed = json.loads(content[start : end + 1])
        if not isinstance(parsed, list):
            return None
        order = [int(x) for x in parsed]
        if sorted(order) != list(range(len(texts))):
            return None
        return order
    except Exception:  # noqa: BLE001 — LLM tier is optional, tier 3 is the fallback
        return None


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    use_llm: bool = True,
    provider: Any | None = None,
    cross_encoder_model: str | None = None,
    max_candidates: int | None = None,
    content_chars: int | None = None,
) -> RerankResult:
    """Rerank candidates for a query; three tiers, honest annotations.

    use_llm=False keeps the pipeline deterministic (eval/CI): the LLM tier
    is skipped entirely, while the local cross-encoder tier still runs.
    """
    n = len(candidates)
    original = list(range(n))
    if n <= 1:
        return RerankResult(
            mode="off", order=original, reason="fewer than two candidates"
        )

    max_c = (
        max_candidates
        if max_candidates is not None
        else _env_int("RERANK_MAX_CANDIDATES", _DEFAULT_MAX_CANDIDATES)
    )
    chars = (
        content_chars
        if content_chars is not None
        else _env_int("RERANK_CONTENT_CHARS", _DEFAULT_CONTENT_CHARS)
    )
    reasons: list[str] = []

    # Tier 1: local cross-encoder (RERANK_MODEL).
    model_name = (
        cross_encoder_model
        if cross_encoder_model is not None
        else os.getenv("RERANK_MODEL", "")
    )
    if model_name:
        encoder = _load_cross_encoder(model_name)
        if encoder is not None:
            texts = [_candidate_text(c, chars) for c in candidates]
            try:
                scores = [float(s) for s in encoder.predict([(query, t) for t in texts])]
                order = sorted(range(n), key=lambda i: scores[i], reverse=True)
                return RerankResult(mode="cross_encoder", order=order, scores=scores)
            except Exception as exc:  # noqa: BLE001 — fall through to tier 2/3
                reasons.append("cross-encoder failed: " + str(exc)[:120])
        else:
            reasons.append(
                "RERANK_MODEL=" + model_name
                + " unavailable (sentence-transformers missing or load failed)"
            )

    # Tier 2: LLM listwise (one JSON call under an input budget).
    if use_llm:
        llm = provider if provider is not None else _llm_provider()
        if llm is not None:
            texts = [_candidate_text(c, chars) for c in candidates[:max_c]]
            llm_order = _llm_order(llm, query, texts)
            if llm_order is not None:
                if max_c < n:
                    llm_order = llm_order + [i for i in range(n) if i not in llm_order]
                return RerankResult(mode="llm", order=llm_order)
            reasons.append("LLM rerank failed (invalid or missing ranking output)")
        else:
            reasons.append("no LLM gateway configured")

    # Tier 3: honest passthrough.
    return RerankResult(
        mode="off",
        order=original,
        reason="; ".join(reasons) if reasons else "no reranker configured",
    )
