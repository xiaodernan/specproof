"""Hybrid retrieval — BM25 + dense-vector RRF fusion (RAG 2.0, 卷IV 4.2).

Pipeline: BM25 (content+symbol) + vector top-k (when embeddings are
available) → Reciprocal Rank Fusion (k=60) → repo_graph neighborhood
expansion (2 hops, 卷IV 4.2) → optional rerank (cross-encoder / LLM /
off) → budget truncation.

Honesty contract (卷IV 4.3): every degradation is annotated in
"HybridOutcome.meta" — no/unusable embeddings, empty vector results,
rerank unavailability — never raised, never silent. ES itself failing is
the caller's contract (the node owns "Elasticsearch unavailable").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from retrieval.embeddings import EmbeddingClient
from retrieval.rerank import RerankResult, rerank

RRF_K = 60
DEFAULT_BM25_SIZE = 20
DEFAULT_VECTOR_K = 10
DEFAULT_EXPAND_TOP = 8
DEFAULT_EXPAND_HOPS = 2

_DocKey = tuple[str, str]


@dataclass
class HybridOutcome:
    """Ordered results + honest metadata for evidence and debugging."""

    results: list[dict[str, Any]]
    meta: dict[str, Any]


def _doc_key(hit: dict[str, Any]) -> _DocKey:
    return (str(hit.get("path", "")), str(hit.get("symbol", "")))


def rrf_fuse(
    bm25_hits: list[dict[str, Any]],
    vector_hits: list[dict[str, Any]],
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Fuse two ranked hit lists with Reciprocal Rank Fusion.

    score(doc) = Σ_lists 1/(k + rank_in_list). Results are sorted by fused
    score desc and carry "rrf_score", per-list ranks and the source label
    (bm25 / vector / bm25+vector). Pure function — no ES call involved.
    """
    fused: dict[_DocKey, dict[str, Any]] = {}
    bm25_keys: set[_DocKey] = set()
    for rank, hit in enumerate(bm25_hits):
        key = _doc_key(hit)
        bm25_keys.add(key)
        base = fused.get(key)
        if base is None:
            base = dict(hit)
            base["rrf_score"] = 0.0
            fused[key] = base
        base["rrf_score"] = float(base["rrf_score"]) + 1.0 / (k + rank)
        base["bm25_rank"] = rank

    vector_keys: set[_DocKey] = set()
    for rank, hit in enumerate(vector_hits):
        key = _doc_key(hit)
        vector_keys.add(key)
        base = fused.get(key)
        if base is None:
            base = dict(hit)
            base["rrf_score"] = 0.0
            fused[key] = base
        base["rrf_score"] = float(base["rrf_score"]) + 1.0 / (k + rank)
        base["vector_rank"] = rank
        if hit.get("vector_score") is not None:
            base["vector_score"] = hit["vector_score"]

    ordered: list[dict[str, Any]] = []
    for key in sorted(fused, key=lambda item: fused[item]["rrf_score"], reverse=True):
        hit = fused[key]
        if key in bm25_keys and key in vector_keys:
            hit["source"] = "bm25+vector"
        elif key in vector_keys:
            hit["source"] = "vector"
        else:
            hit["source"] = "bm25"
        ordered.append(hit)
    return ordered


def hybrid_search(
    es: Any,
    query: str,
    repo: str,
    k: int = 16,
    graph: Any | None = None,
    *,
    embedder: EmbeddingClient | None = None,
    commit_sha: str | None = None,
    use_llm: bool = True,
    hops: int = DEFAULT_EXPAND_HOPS,
    expand_top: int = DEFAULT_EXPAND_TOP,
) -> HybridOutcome:
    """Run the RAG 2.0 hybrid pipeline against an ElasticsearchStore-like "es".

    Degradations (卷IV 4.3) are annotated in meta, never raised:
    no/unusable embeddings → BM25+graph order (mode="bm25"); empty vector
    results → automatic BM25 fallback without error; rerank unavailable →
    rerank_mode="off" with the original order preserved.
    """
    if not query.strip():
        return HybridOutcome(
            [],
            {
                "mode": "bm25",
                "embedding_used": None,
                "embedding_error": None,
                "bm25_hits": 0,
                "vector_hits": 0,
                "rrf_k": RRF_K,
                "hops": hops,
                "expanded": 0,
                "rerank_mode": "off",
                "rerank_reason": "empty query",
                "returned": 0,
                "truncated": False,
            },
        )

    bm25_hits: list[dict[str, Any]] = es.search_code(
        repo, query, size=DEFAULT_BM25_SIZE
    )

    vector_hits: list[dict[str, Any]] = []
    vector_error: str | None = None
    embedding_used: str | None = None
    vector_used = False
    if embedder is not None and embedder.configured:
        vectors, reason = embedder.embed([query])
        if vectors is None:
            vector_error = reason
        else:
            embedding_used = embedder.model
            try:
                vector_hits = es.vector_search(
                    repo, vectors[0], k=DEFAULT_VECTOR_K, commit_sha=commit_sha
                )
            except Exception as exc:  # noqa: BLE001 — vector channel is optional
                vector_error = "vector_search failed: " + str(exc)[:120]
            if vector_hits:
                vector_used = True

    fused = rrf_fuse(bm25_hits, vector_hits, k=RRF_K)

    if graph is not None and fused:
        seeds = fused[:expand_top]
        expanded = graph.expand_hits(seeds, hops=hops)
        merged = list(expanded) if expanded else [dict(h) for h in seeds]
    else:
        merged = [dict(h) for h in fused]
    expanded_count = max(0, len(merged) - len(fused))

    rerank_outcome: RerankResult
    if vector_used and len(merged) > 1:
        try:
            rerank_outcome = rerank(query, merged, use_llm=use_llm)
        except Exception as exc:  # noqa: BLE001 — rerank is optional
            rerank_outcome = RerankResult(
                mode="off",
                order=list(range(len(merged))),
                reason="rerank failed: " + str(exc)[:120],
            )
        merged = [merged[i] for i in rerank_outcome.order]
    else:
        rerank_outcome = RerankResult(
            mode="off",
            order=list(range(len(merged))),
            reason="rerank skipped (bm25-only mode, 卷IV 4.3)" if merged else None,
        )

    final: list[dict[str, Any]] = []
    for rank, hit in enumerate(merged[:k]):
        item = dict(hit)
        item["rank"] = rank
        final.append(item)

    meta: dict[str, Any] = {
        "mode": "hybrid" if vector_used else "bm25",
        "embedding_used": embedding_used,
        "embedding_error": vector_error,
        "bm25_hits": len(bm25_hits),
        "vector_hits": len(vector_hits),
        "rrf_k": RRF_K,
        "hops": hops,
        "expanded": expanded_count,
        "rerank_mode": rerank_outcome.mode,
        "rerank_reason": rerank_outcome.reason,
        "returned": len(final),
        "truncated": len(merged) > k,
    }
    return HybridOutcome(results=final, meta=meta)
