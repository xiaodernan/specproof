"""Unit tests for retrieval provenance fields (commit/line, §14)."""

from __future__ import annotations

from typing import Any

import pytest

import agent.nodes.retrieve_repository_context as retrieve


class FakeStore:
    """Minimal ES stand-in: search returns docs with provenance fields."""

    def is_ready(self) -> bool:
        return True

    def index_repository(self, repo, commit_sha, files, **kwargs):
        return 1

    def index_with_embeddings(self, repo, commit_sha, files, embedder, **kwargs):
        return {"indexed": 1, "embedded": 1}

    def search_code(self, repo, query, commit_sha=None, size=20):
        return [{
            "path": "Svc.java",
            "symbol": "send",
            "content": "void send() {}",
            "source": "bm25",
            "commit_sha": "abc123",
            "start_line": 10,
            "end_line": 14,
        }]


@pytest.fixture()
def fake_graph(monkeypatch):
    class FakeGraph:
        def expand_hits(self, hits, hops=1):
            return hits

    monkeypatch.setattr("agent.repo_graph.RepoGraph", lambda files: FakeGraph())


def _state(tmp_path) -> dict[str, Any]:
    ws = tmp_path / "ws"
    (ws / "src" / "main" / "java").mkdir(parents=True)
    (ws / "src" / "main" / "java" / "Svc.java").write_text(
        "class Svc { void send() {} }", encoding="utf-8",
    )
    return {
        "repo_path": "repo:demo",
        "base_workspace": "",
        "head_workspace": str(ws),
        "requirement_text": "email change event",
        "use_llm": False,
        "job_id": "j1",
    }


def test_bm25_context_carries_commit_and_lines(fake_graph, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: FakeStore())
    out = retrieve.retrieve_repository_context_node(_state(tmp_path))
    assert out["repo_context"][0]["commit_sha"] == "abc123"
    assert out["repo_context"][0]["start_line"] == 10
    assert out["repo_context"][0]["end_line"] == 14


def test_bm25_context_missing_provenance_falls_back(fake_graph, monkeypatch, tmp_path) -> None:
    class NoProvenanceStore(FakeStore):
        def search_code(self, repo, query, commit_sha=None, size=20):
            return [{
                "path": "Svc.java",
                "symbol": "send",
                "content": "void send() {}",
            }]

    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: NoProvenanceStore())
    out = retrieve.retrieve_repository_context_node(_state(tmp_path))
    entry = out["repo_context"][0]
    # Honest fallback: the doc carried no provenance and git rev-parse
    # cannot run on the temp repo — the field stays empty, never guessed.
    assert entry["commit_sha"] == ""
    assert entry["start_line"] is None
    assert entry["end_line"] is None
