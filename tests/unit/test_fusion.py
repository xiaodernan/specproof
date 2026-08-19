"""Unit tests for retrieval/fusion.py — additive RRF + graph-neighbor boost.

Regression coverage for the 48.9% ablation bug (2026-08-18): the old
pipeline REPLACED the fused semantic ranks with top-8 seed neighborhoods.
These tests pin the additive contract instead: graph boost appends, never
displaces, never duplicates; RRF is deterministic and handles empty input.
"""
from __future__ import annotations

from typing import Any

import pytest

from retrieval.fusion import RRF_K, GraphBoost, doc_key, graph_boost, rrf_fuse


def _hit(path: str, symbol: str, **extra: Any) -> dict[str, Any]:
    hit: dict[str, Any] = {"path": path, "symbol": symbol}
    hit.update(extra)
    return hit


# ── RRF ordering / determinism ──────────────────────────────────────────────


def test_rrf_two_list_formula_and_source_labels():
    bm25 = [_hit("a.py", "A"), _hit("b.py", "B")]
    symbol = [_hit("b.py", "B"), _hit("c.py", "C")]
    fused = rrf_fuse([bm25, symbol], k=60, labels=["hybrid_semantic", "symbol"])
    assert [h["symbol"] for h in fused] == ["B", "A", "C"]
    assert fused[0]["rrf_score"] == pytest.approx(1 / 60 + 1 / 61)
    assert fused[1]["rrf_score"] == pytest.approx(1 / 60)
    assert fused[2]["rrf_score"] == pytest.approx(1 / 61)
    assert fused[0]["source"] == "hybrid_semantic+symbol"
    assert fused[1]["source"] == "hybrid_semantic"
    assert fused[2]["source"] == "symbol"
    assert fused[0]["rrf_ranks"] == [1, 0]
    assert fused[1]["rrf_ranks"] == [0, None]
    assert fused[2]["rrf_ranks"] == [None, 1]


def test_rrf_ordering_is_deterministic_across_calls_and_input_order():
    lists = [
        [_hit("a.py", "A"), _hit("b.py", "B"), _hit("c.py", "C")],
        [_hit("c.py", "C"), _hit("b.py", "B")],
        [_hit("b.py", "B")],
    ]
    first = rrf_fuse(lists)
    second = rrf_fuse([list(lst) for lst in lists])
    assert [doc_key(h) for h in first] == [doc_key(h) for h in second]
    assert first == second  # identical metadata, identical order
    permuted = rrf_fuse([lists[2], lists[0], lists[1]])
    assert [doc_key(h) for h in permuted] == [doc_key(h) for h in first]


def test_rrf_tie_breaks_deterministically_by_path():
    fused = rrf_fuse([[_hit("b.py", "B")], [_hit("a.py", "A")]])
    assert [doc_key(h) for h in fused] == [("a.py", "A"), ("b.py", "B")]


def test_rrf_counts_duplicate_doc_once_at_best_rank():
    fused = rrf_fuse([[_hit("a.py", "A"), _hit("a.py", "A"), _hit("b.py", "B")]])
    assert [h["symbol"] for h in fused] == ["A", "B"]
    assert fused[0]["rrf_score"] == pytest.approx(1 / 60)
    assert fused[0]["rrf_ranks"] == [0]


# ── empty / invalid input edges ─────────────────────────────────────────────


def test_rrf_empty_input_edges():
    assert rrf_fuse([]) == []
    assert rrf_fuse([[], []]) == []
    fused = rrf_fuse([[], [_hit("a.py", "A")]])
    assert [h["symbol"] for h in fused] == ["A"]
    assert fused[0]["rrf_score"] == pytest.approx(1 / 60)


def test_rrf_rejects_nonpositive_k():
    with pytest.raises(ValueError):
        rrf_fuse([[_hit("a.py", "A")]], k=0)


def test_rrf_rejects_mismatched_labels():
    with pytest.raises(ValueError):
        rrf_fuse([[_hit("a.py", "A")]], labels=["only_one", "extra"])


# ── symbol integration shape ────────────────────────────────────────────────


def test_rrf_symbol_integration_shape():
    symbol_hits = [
        {
            "path": "agent/repo_graph.py",
            "symbol": "RepoGraph",
            "line": 10,
            "content": "class RepoGraph:",
            "language": "python",
            "source": "symbol_index",
            "score": 10.0,
        }
    ]
    bm25 = [_hit("craft/loop.py", "craft/loop.py")]
    fused = rrf_fuse([bm25, symbol_hits], labels=["hybrid_semantic", "symbol"])
    symbol_only = [h for h in fused if h["symbol"] == "RepoGraph"]
    assert len(symbol_only) == 1
    hit = symbol_only[0]
    assert hit["source"] == "symbol"
    assert hit["rrf_ranks"] == [None, 0]
    assert hit["rrf_score"] == pytest.approx(1 / RRF_K)
    assert hit["line"] == 10
    assert hit["content"] == "class RepoGraph:"


# ── graph boost: the 48.9% regression ───────────────────────────────────────


def test_graph_boost_never_displaces_existing_fused_hits():
    fused = [_hit("a.py", "A"), _hit("b.py", "B"), _hit("c.py", "C")]
    neighbors = [_hit("d.py", "D"), _hit("a.py", "A"), _hit("e.py", "E")]
    boosted = graph_boost(fused, neighbors)
    assert boosted[:3] == fused  # semantic ranks: same content, same order
    assert [h["symbol"] for h in boosted[3:]] == ["D", "E"]  # a.py not duplicated
    assert all(h["source"] == "graph_boost" for h in boosted[3:])
    assert all(h["graph_boosted"] is True for h in boosted[3:])


def test_graph_boost_appends_after_full_fused_list():
    fused = [_hit("a.py", "A"), _hit("b.py", "B")]
    boosted = graph_boost(fused, [_hit("c.py", "C")])
    assert [h["symbol"] for h in boosted] == ["A", "B", "C"]


def test_graph_boost_inputs_never_mutated():
    fused = [_hit("a.py", "A")]
    neighbors = [_hit("b.py", "B")]
    fused_snapshot = [dict(h) for h in fused]
    neighbors_snapshot = [dict(h) for h in neighbors]
    graph_boost(fused, neighbors)
    assert fused == fused_snapshot
    assert neighbors == neighbors_snapshot


def test_graph_boost_max_cap_and_neighbor_dedup():
    fused = [_hit("a.py", "A")]
    neighbors = [_hit("b.py", "B"), _hit("c.py", "C"), _hit("b.py", "B")]
    boosted = GraphBoost(max_boost=1).boost(fused, neighbors)
    assert [h["symbol"] for h in boosted] == ["A", "B"]
    capped = graph_boost([], neighbors, max_boost=2)
    assert [h["symbol"] for h in capped] == ["B", "C"]


def test_graph_boost_empty_edges():
    assert graph_boost([], []) == []
    assert graph_boost([_hit("x.py", "X")], []) == [_hit("x.py", "X")]
    single = graph_boost([], [_hit("a.py", "A")])
    assert single[0]["source"] == "graph_boost"
    assert single[0]["graph_boosted"] is True
    assert GraphBoost(max_boost=0).boost(
        [_hit("a.py", "A")], [_hit("b.py", "B")]
    ) == [_hit("a.py", "A")]


def test_graph_boost_rejects_negative_cap():
    with pytest.raises(ValueError):
        GraphBoost(max_boost=-1)
