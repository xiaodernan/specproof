"""Retrieval-context node execution tests (#195) — honest counters at the
node boundary, written WITH the landing (not backfilled).

The late-imported seams (storage.elasticsearch.ElasticsearchStore,
agent.repo_graph.RepoGraph, retrieval.embeddings.EmbeddingClient,
retrieval.hybrid.hybrid_search) and the git rev-parse subprocess are
stubbed at their import sources; the client-side pieces (reading the
workspace, query building) run for real. One case per outcome word in
RETRIEVE_OUTCOMES:

- hybrid_rrf: embeddings configured — the hybrid pipeline runs (witness:
  index_with_embeddings called, search_code never reached);
- bm25_graph: no embeddings — deterministic BM25 + graph (witness: the
  hybrid search stub would raise);
- no_workspace: empty head workspace — _read_java_files is never reached
  (witness: it would raise);
- no_java_sources: workspace without Java sources — store and subprocess
  are never reached (witness: both would raise);
- es_unavailable: is_ready False — the documented honesty contract, empty
  context, and nothing runs after the readiness probe;
- retrieval_failed: search raised — degraded to an empty context naming the
  exception's type in the note (its message only in the log, #524);

plus retrieve_repository_context_runs_total on every path and a drift
gate binding the parity family's regex words to RETRIEVE_OUTCOMES and to
the source literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agent.nodes.retrieve_repository_context as retrieve_module
from agent.nodes.retrieve_repository_context import (
    RETRIEVE_OUTCOMES,
    retrieve_repository_context_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("retrieve_repository_context_runs_total",) + tuple(
    f"retrieve_repository_context_outcomes_{word}_total"
    for word in sorted(RETRIEVE_OUTCOMES)
)

_HIT = {
    "path": "Svc.java",
    "symbol": "send",
    "content": "void send() {}",
    "source": "bm25",
    "commit_sha": "deadbeef",
    "start_line": 10,
    "end_line": 14,
}


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["retrieve_repository_context_runs_total"] = 1.0
    for word in words:
        deltas[f"retrieve_repository_context_outcomes_{word}_total"] = 1.0
    return deltas


class _FakeStore:
    """Minimal ES stand-in; records which API surface was exercised."""

    def __init__(
        self,
        *,
        ready: bool = True,
        hits: list[dict[str, Any]] | None = None,
        search_error: Exception | None = None,
    ) -> None:
        self._ready = ready
        self._hits = hits or []
        self._search_error = search_error
        self.calls: list[str] = []

    def is_ready(self) -> bool:
        self.calls.append("is_ready")
        return self._ready

    def index_repository(self, repo, commit_sha, files, **kwargs):
        self.calls.append("index_repository")
        return len(files)

    def index_with_embeddings(self, repo, commit_sha, files, embedder, **kwargs):
        self.calls.append("index_with_embeddings")
        return {"indexed": len(files), "embedded": len(files)}

    def search_code(self, repo, query, commit_sha=None, size=20):
        self.calls.append("search_code")
        if self._search_error is not None:
            raise self._search_error
        return self._hits


def _stub_git_rev_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        retrieve_module, "subprocess",
        SimpleNamespace(
            run=lambda *a, **k: SimpleNamespace(
                returncode=0, stdout="deadbeef\n", stderr=""
            )
        ),
    )


def _stub_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent.repo_graph.RepoGraph",
        lambda files: SimpleNamespace(expand_hits=lambda hits, hops=1: hits),
    )


def _stub_embedder(monkeypatch: pytest.MonkeyPatch, *, configured: bool) -> None:
    class _Embedder:
        pass

    _Embedder.configured = configured  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "retrieval.embeddings.EmbeddingClient",
        SimpleNamespace(from_env=lambda: _Embedder()),
    )


def _state(tmp_path: Path, *, java: bool = True) -> dict[str, Any]:
    ws = tmp_path / "ws"
    if java:
        java_dir = ws / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "Svc.java").write_text(
            "class Svc { void send() {} }", encoding="utf-8",
        )
    else:
        ws.mkdir(parents=True)
    return {
        "repo_path": str(tmp_path / "repo"),
        "head_workspace": str(ws),
        "requirement_text": "email change event",
        "use_llm": False,
        "job_id": "j1",
    }


def test_hybrid_rrf_counts_hybrid_rrf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = _FakeStore()
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)
    _stub_git_rev_parse(monkeypatch)
    _stub_graph(monkeypatch)
    _stub_embedder(monkeypatch, configured=True)

    hybrid_hits = [{**_HIT, "source": "hybrid", "rank": 1, "rrf_score": 0.5}]

    def fake_hybrid_search(**kwargs: Any) -> Any:
        return SimpleNamespace(
            meta={
                "mode": "hybrid_rrf",
                "bm25_hits": 3,
                "vector_hits": 2,
                "rerank_mode": "off",
                "embedding_used": True,
            },
            results=hybrid_hits,
        )

    monkeypatch.setattr("retrieval.hybrid.hybrid_search", fake_hybrid_search)

    before = _before()
    result = retrieve_repository_context_node(_state(tmp_path))  # type: ignore[arg-type]

    assert result["retrieval_note"].startswith("hybrid_rrf mode=hybrid_rrf")
    assert result["repo_context"][0]["source"] == "hybrid"
    assert "index_with_embeddings" in store.calls
    assert "search_code" not in store.calls, (
        "the hybrid path must not touch the BM25 search API directly"
    )
    assert _deltas(before) == _only("hybrid_rrf")


def test_bm25_graph_counts_bm25_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = _FakeStore(hits=[dict(_HIT)])
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)
    _stub_git_rev_parse(monkeypatch)
    _stub_graph(monkeypatch)
    _stub_embedder(monkeypatch, configured=False)

    def bomb_hybrid(**kwargs: Any) -> Any:
        raise AssertionError("hybrid_search must not run without a configured embedder")

    monkeypatch.setattr("retrieval.hybrid.hybrid_search", bomb_hybrid)

    before = _before()
    result = retrieve_repository_context_node(_state(tmp_path))  # type: ignore[arg-type]

    assert result["retrieval_note"] == "Indexed 1 symbol chunks; 1 retrieved"
    assert result["repo_context"][0]["source"] == "bm25"
    assert "index_with_embeddings" not in store.calls
    assert _deltas(before) == _only("bm25_graph")


def test_no_workspace_counts_no_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bomb_reader(workspace: str) -> dict[str, str]:
        raise AssertionError("no workspace must short-circuit before any I/O")

    monkeypatch.setattr(retrieve_module, "_read_java_files", bomb_reader)

    before = _before()
    result = retrieve_repository_context_node({"head_workspace": ""})  # type: ignore[arg-type]

    assert result == {
        "repo_context": [],
        "retrieval_note": "No head workspace — repository retrieval skipped",
    }
    assert _deltas(before) == _only("no_workspace")


def test_no_java_sources_counts_no_java_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def bomb_store() -> None:
        raise AssertionError("no sources must short-circuit before infra")

    def bomb_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no sources must short-circuit before git")

    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", bomb_store)
    monkeypatch.setattr(retrieve_module, "subprocess", SimpleNamespace(run=bomb_run))

    before = _before()
    result = retrieve_repository_context_node(_state(tmp_path, java=False))  # type: ignore[arg-type]

    assert result == {
        "repo_context": [],
        "retrieval_note": "No Java sources in head workspace — nothing to index",
    }
    assert _deltas(before) == _only("no_java_sources")


def test_es_unavailable_counts_es_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = _FakeStore(ready=False)
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)
    _stub_git_rev_parse(monkeypatch)

    before = _before()
    result = retrieve_repository_context_node(_state(tmp_path))  # type: ignore[arg-type]

    assert result == {
        "repo_context": [],
        "retrieval_note": "Elasticsearch unavailable — retrieval skipped",
    }
    assert store.calls == ["is_ready"], (
        "nothing may run after the readiness probe refuses"
    )
    assert _deltas(before) == _only("es_unavailable")


def test_retrieval_failed_counts_retrieval_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = _FakeStore(search_error=RuntimeError("boom"))
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)
    _stub_git_rev_parse(monkeypatch)
    _stub_graph(monkeypatch)
    _stub_embedder(monkeypatch, configured=False)

    before = _before()
    result = retrieve_repository_context_node(_state(tmp_path))  # type: ignore[arg-type]

    assert result == {
        "repo_context": [],
        # The type, not the message: this handler wraps a bulk index of the
        # repository's own source, and Elasticsearch quotes the document it
        # rejected (#524). The message goes to the log.
        "retrieval_note": "Repository retrieval failed: RuntimeError",
    }
    assert _deltas(before) == _only("retrieval_failed")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (
        ROOT / "agent" / "nodes" / "retrieve_repository_context.py"
    ).read_text(encoding="utf-8")
    literals = set(
        re.findall(
            # [a-z0-9_]: the vocabulary contains bm25_graph — a [a-z_]+
            # class silently misses it and "literals == vocabulary" then
            # fails on MY regex, not on a real drift.
            r'incr\("retrieve_repository_context_outcomes_([a-z0-9_]+)_total"\)',
            source,
        )
    )
    assert literals == set(RETRIEVE_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(RETRIEVE_OUTCOMES)}"
    )
    assert source.count('incr("retrieve_repository_context_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["retrieve_repository_context"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(RETRIEVE_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(RETRIEVE_OUTCOMES)}"
    )
