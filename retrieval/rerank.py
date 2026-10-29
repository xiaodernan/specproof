"""Rerank layer (RAG 2.0, 卷IV 4.2/4.3) — three tiers, each degradation named.

Tier 1 (cross-encoder): RERANK_MODEL names a sentence-transformers
cross-encoder. sentence-transformers is an OPTIONAL dependency (not in
pyproject.toml) — an import/load failure means this tier is unavailable,
never a crash.

Tier 2 (LLM listwise): when the LLM gateway is configured, one JSON
listwise call under an input budget (candidate count × content chars).
Anything that keeps that call from producing a ranking — a reply with no
array in it, a reply that is not the requested permutation, a gateway that
errored, a wait that expired — falls back to tier 3, and each of those gets
its own name.

Tier 3 (off): original order preserved, annotated with a *reason* (free
text, for whoever reads the dict) and a *cause* drawn from a closed
vocabulary. 卷IV 4.3: 重排模型缺失 → rerank=off 保序.

The vocabulary exists because the reason cannot leave this module.  A
reason quotes the text of a raised exception, and the request that raised
it carried repository source; the field that operators actually see —
`retrieval_note`, persisted in the run summary and put on notifications —
is built by the caller, so the caller may forward codes and must not
forward sentences.  Before #523 the caller forwarded neither, and every
exception from tier 2 was reported as a malformed answer.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
from dataclasses import dataclass
from typing import Any

from retrieval._env import env_int as _env_int

_DEFAULT_MAX_CANDIDATES = 20
_DEFAULT_CONTENT_CHARS = 200
#: Seconds the calling thread waits for the listwise answer before reporting a
#: degraded rerank.  This is a *reporting* bound, not a cancellation bound: the
#: worker thread keeps running the provider's own retry policy to its end, which
#: is longer than this wait whenever the gateway accepts the connection and
#: stays silent (the per-attempt request timeout times the attempt budget).
_LLM_WAIT_SECONDS = 90.0
_cross_encoder_cache: dict[str, Any] = {}

#: Every degradation this layer can distinguish.  A code is the only failure fact
#: allowed out of `retrieval/` into an observable field; `RERANK_CAUSES` is closed
#: on purpose, and a new exit that is not in it is a new fact nobody can see.
RERANK_CAUSES: frozenset[str] = frozenset(
    {
        "single_candidate",
        "not_configured",
        "cross_encoder_unavailable",
        "cross_encoder_failed",
        "llm_not_configured",
        "llm_provider_stack_unavailable",
        "llm_output_no_json_array",
        "llm_output_malformed_json",
        "llm_output_not_an_index_list",
        "llm_output_not_a_permutation",
        "llm_provider_error",
        "llm_wait_timeout",
        "bm25_only",
        "rerank_crashed",
        "empty_query",
    }
)


class _RerankWaitTimeoutError(TimeoutError):
    """The wait for the answer expired; the call may still be running elsewhere."""


@dataclass
class RerankResult:
    """Outcome of one rerank call: mode + a permutation of the candidates.

    ``reason`` is a sentence for whoever reads the dict; ``causes`` holds one code
    per degradation the earlier tiers reported, in the same order as those
    sentences.  Codes are the part the caller is allowed to forward.
    """

    mode: str  # "cross_encoder" | "llm" | "off"
    order: list[int]
    scores: list[float] | None = None
    reason: str | None = None
    causes: tuple[str, ...] = ()


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


def _llm_provider() -> tuple[Any | None, str | None]:
    """The gateway provider from env, or the code saying why there is none.

    Two different absences share this door: the gateway is not configured, and
    the gateway is configured but the provider stack will not import.  Before
    #523 both returned ``None`` and the caller called both "not configured".
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None, "llm_not_configured"
    try:
        from providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(probe_on_init=False), None
    except Exception:  # noqa: BLE001 — provider stack optional for rerank
        return None, "llm_provider_stack_unavailable"


def _run_async(coro: Any) -> Any:
    """Run an async provider call from a sync context (nodes are sync).

    Waiting longer than ``_LLM_WAIT_SECONDS`` raises :class:`_RerankWaitTimeoutError`
    rather than a bare ``TimeoutError``, so a caller can tell "the answer did not
    arrive" from "the gateway answered with an error".  The worker thread is still
    joined when the executor closes, so the wall clock can run past the wait: this
    bound decides what gets reported, not what gets cancelled.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        try:
            return future.result(timeout=_LLM_WAIT_SECONDS)
        except concurrent.futures.TimeoutError as exc:
            raise _RerankWaitTimeoutError(
                f"no rerank answer within {_LLM_WAIT_SECONDS:g}s"
            ) from exc


def _llm_order(
    provider: Any, query: str, texts: list[str]
) -> tuple[list[int] | None, str, str]:
    """Ask the LLM for a best-first permutation of candidate indices.

    Returns ``(order, cause, detail)``: ``cause`` is ``""`` exactly when
    ``order`` is not, and ``detail`` is the full sentence for what happened.
    Never a partial ranking.  An absent array, unparsable JSON, a list that is not
    indices, a non-permutation, a gateway error and an expired wait are six
    different facts; before #523 all six were one sentence about the reply.
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
    except _RerankWaitTimeoutError:
        return (
            None,
            "llm_wait_timeout",
            f"LLM rerank got no reply within {_LLM_WAIT_SECONDS:g}s",
        )
    except Exception as exc:  # noqa: BLE001 — every gateway error degrades to tier 3
        return None, "llm_provider_error", "LLM rerank call raised " + type(exc).__name__
    content = response.content or ""
    start = content.find("[")
    end = content.rfind("]")
    if start < 0 or end <= start:
        return None, "llm_output_no_json_array", "LLM rerank found no JSON array in the reply"
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None, "llm_output_malformed_json", "LLM rerank found a span that is not JSON"
    if not isinstance(parsed, list):
        return None, "llm_output_not_an_index_list", "LLM rerank got a reply that is not a list"
    try:
        order = [int(x) for x in parsed]
    except (TypeError, ValueError):
        return (
            None,
            "llm_output_not_an_index_list",
            "LLM rerank got a list whose entries are not indices",
        )
    if sorted(order) != list(range(len(texts))):
        return (
            None,
            "llm_output_not_a_permutation",
            "LLM rerank got a reply that is not a permutation of the "
            f"{len(texts)} candidates",
        )
    return order, "", ""


_ABSENCE_SENTENCES = {
    "llm_not_configured": "no LLM gateway configured",
    "llm_provider_stack_unavailable": (
        "the LLM gateway is configured but its provider stack is unavailable"
    ),
}


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
    """Rerank candidates for a query; three tiers, annotated with cause codes.

    use_llm=False keeps the pipeline deterministic (eval/CI): the LLM tier
    is skipped entirely, while the local cross-encoder tier still runs.
    """
    n = len(candidates)
    original = list(range(n))
    if n <= 1:
        return RerankResult(
            mode="off",
            order=original,
            reason="fewer than two candidates",
            causes=("single_candidate",),
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
    #: (code, sentence) pairs, so the two views of one degradation cannot drift:
    #: the caller may forward the codes, and only the codes.
    notes: list[tuple[str, str]] = []

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
                notes.append(("cross_encoder_failed", "cross-encoder failed: " + str(exc)[:120]))
        else:
            notes.append(
                (
                    "cross_encoder_unavailable",
                    "RERANK_MODEL=" + model_name
                    + " unavailable (sentence-transformers missing or load failed)",
                )
            )

    # Tier 2: LLM listwise (one JSON call under an input budget).
    if use_llm:
        llm: Any | None
        absence: str | None
        if provider is not None:
            llm, absence = provider, None
        else:
            llm, absence = _llm_provider()
        if llm is not None:
            texts = [_candidate_text(c, chars) for c in candidates[:max_c]]
            llm_order, cause, detail = _llm_order(llm, query, texts)
            if llm_order is not None:
                if max_c < n:
                    llm_order = llm_order + [i for i in range(n) if i not in llm_order]
                return RerankResult(mode="llm", order=llm_order)
            notes.append((cause, detail))
        else:
            code = absence if absence is not None else "llm_not_configured"
            notes.append((code, _ABSENCE_SENTENCES[code]))

    # Tier 3: passthrough, annotated with whatever the earlier tiers reported.
    return RerankResult(
        mode="off",
        order=original,
        reason="; ".join(text for _, text in notes) or "no reranker configured",
        causes=tuple(code for code, _ in notes) or ("not_configured",),
    )
