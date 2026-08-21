"""Additive retrieval fusion — N-list RRF + graph-neighbor boost (RAG 2.0, 卷IV 4.2).

This module is the corrected successor to the 2026-08-18 graph ablation
(48.9% recall): the old pipeline REPLACED the fused semantic ranking with
top-8 seed neighborhoods (retrieval/hybrid.py: `merged = list(expanded)`).
The result was that graph neighbors displaced BM25/vector/symbol hits and
buried the expected files.

Contract here (卷IV 4.3 honesty, additive-only):

- `rrf_fuse` is a pure N-list Reciprocal Rank Fusion: the semantic lists
  (hybrid_semantic BM25, vector, symbol) are summed into one ranking and
  nothing is ever removed or reordered by a later stage.
- `GraphBoost` only ADDS graph neighbors as supplemental candidates when
  they are not already present in the fused list, appended AFTER it. It
  never replaces, reorders or duplicates existing semantic ranks.

Vector results are optional: callers hand an empty list when embeddings are
unavailable, and the fusion degrades to the remaining lists without error.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

RRF_K = 60
DEFAULT_BOOST_MAX = 10
_MISSING_RANK = 10**9

_DocKey = tuple[str, str]


def doc_key(hit: dict[str, Any]) -> _DocKey:
    """Identity of one hit across ranked lists: (path, symbol)."""
    return (str(hit.get("path", "")), str(hit.get("symbol", "")))


def _best_rank(hit: dict[str, Any]) -> int:
    ranks = hit.get("rrf_ranks") or []
    present = [rank for rank in ranks if rank is not None]
    return min(present) if present else _MISSING_RANK


def rrf_fuse(
    results_lists: Sequence[list[dict[str, Any]]],
    k: int = RRF_K,
    labels: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Fuse N ranked hit lists with Reciprocal Rank Fusion.

    score(doc) = Σ_lists 1/(k + rank_in_list); a doc repeated inside one
    list is counted once, at its best rank. Empty lists contribute nothing.
    Ties are broken deterministically: best per-list rank, then (path,
    symbol). Fused hits carry "rrf_score", "rrf_ranks" (one rank per input
    list, None when absent) and "source" ("+"-joined labels of the lists
    that contributed). Pure function — no ES call involved.

    labels names the input lists for "source" (defaults to list_0..list_N).
    """
    if k <= 0:
        raise ValueError(f"k must be positive, got {k}")
    lists = list(results_lists)
    names = list(labels) if labels is not None else [f"list_{i}" for i in range(len(lists))]
    if len(names) != len(lists):
        raise ValueError(f"labels length {len(names)} != results_lists length {len(lists)}")
    fused: dict[_DocKey, dict[str, Any]] = {}
    sources: dict[_DocKey, list[str]] = {}
    for idx, hits in enumerate(lists):
        if not hits:
            continue
        name = names[idx]
        for rank, hit in enumerate(hits):
            key = doc_key(hit)
            base = fused.get(key)
            if base is None:
                base = dict(hit)
                base["rrf_score"] = 0.0
                base["rrf_ranks"] = [None] * len(lists)
                fused[key] = base
            if base["rrf_ranks"][idx] is None:  # best rank in this list wins
                base["rrf_ranks"][idx] = rank
                base["rrf_score"] = float(base["rrf_score"]) + 1.0 / (k + rank)
                sources.setdefault(key, []).append(name)
    ordered: list[dict[str, Any]] = []
    for key, hit in fused.items():
        hit["source"] = "+".join(sources[key])
        ordered.append(hit)
    ordered.sort(
        key=lambda hit: (
            -float(hit["rrf_score"]),
            _best_rank(hit),
            str(hit.get("path", "")),
            str(hit.get("symbol", "")),
        )
    )
    return ordered


@dataclass(frozen=True)
class GraphBoost:
    """Graph-neighbor supplement policy (additive-only, 卷IV 4.2).

    Regression guard for the 48.9% ablation bug: the fused semantic ranking
    is returned verbatim as the prefix of the output, and graph neighbors
    are appended AFTER it — only when their (path, symbol) key is not
    already present in the fused list. Existing ranks are never displaced,
    replaced or reordered. max_boost caps the number of appended candidates.
    """

    max_boost: int = DEFAULT_BOOST_MAX

    def __post_init__(self) -> None:
        if self.max_boost < 0:
            raise ValueError(f"max_boost must be >= 0, got {self.max_boost}")

    def boost(
        self,
        fused: list[dict[str, Any]],
        neighbors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return fused (unchanged, copied) with new neighbors appended."""
        out = [dict(hit) for hit in fused]
        if self.max_boost == 0:
            return out
        present = {doc_key(hit) for hit in fused}
        added = 0
        for neighbor in neighbors:
            if added >= self.max_boost:
                break
            key = doc_key(neighbor)
            if key in present:
                continue
            item = dict(neighbor)
            item["source"] = "graph_boost"
            item["graph_boosted"] = True
            out.append(item)
            present.add(key)
            added += 1
        return out


def graph_boost(
    fused: list[dict[str, Any]],
    neighbors: list[dict[str, Any]],
    max_boost: int = DEFAULT_BOOST_MAX,
) -> list[dict[str, Any]]:
    """Pure convenience wrapper around GraphBoost.boost."""
    return GraphBoost(max_boost=max_boost).boost(fused, neighbors)


__all__ = [
    "DEFAULT_BOOST_MAX",
    "RRF_K",
    "GraphBoost",
    "doc_key",
    "graph_boost",
    "rrf_fuse",
]
