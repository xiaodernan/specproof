"""Backlog #10 production wiring — ES projection cleanup (all offline).

Covers the two wiring points added on top of storage/elasticsearch.py's
delete_projection / count_projection_docs:

1. agent/nodes/retrieve_repository_context.py passes the state's job_id
   down to index_with_embeddings / index_repository (hybrid and BM25
   paths). When the state carries no job_id (CLI / eval runs, or the
   empty-string initial_state default) the kwarg is omitted entirely, so
   the store default (None = no stamp, pre-#10 document shape) applies.
2. agent/worker.cleanup_job_projection(job_id) — the standalone cleanup
   entry for the data-lifecycle job deletion (DATA_LIFECYCLE §3.4): it
   calls ElasticsearchStore.delete_projection(job_id=...) once per job,
   is idempotent (second call returns 0), closes the store, and stays
   best-effort when Elasticsearch is unavailable. It is deliberately not
   wired into the worker terminal path — retrieval projections are audit
   evidence.

No real Elasticsearch, no network: recording fakes and an in-memory fake
ES client only.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.state import Phase0State
from agent.worker import cleanup_job_projection
from retrieval.hybrid import HybridOutcome
from storage.elasticsearch import ElasticsearchStore


def _hit(path: str, symbol: str, content: str = "x") -> dict[str, Any]:
    return {"path": path, "symbol": symbol, "content": content}


class RecordingStore:
    """ES store stand-in recording the index-call kwargs the node passed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def is_ready(self) -> bool:
        return True

    def index_repository(
        self, repo: str, commit_sha: str, files: dict[str, str], **kwargs: Any
    ) -> int:
        self.calls.append(("index_repository", dict(kwargs)))
        return 3

    def search_code(
        self, repo: str, query: str, commit_sha: str | None = None, size: int = 20
    ) -> list[dict[str, Any]]:
        return [_hit("com/x/Service.java", "changeEmail")]

    def index_with_embeddings(
        self,
        repo: str,
        commit_sha: str,
        files: dict[str, str],
        embedder: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(("index_with_embeddings", dict(kwargs)))
        return {
            "indexed": 3,
            "embedded": 3,
            "vectors_skipped": 0,
            "embedding_notes": [],
        }


def _make_state(tmp_path: Path, job_id: str | None = None) -> dict[str, Any]:
    """Node input state with one real Java file; job_id key only when given."""
    src = tmp_path / "src" / "main" / "java" / "com" / "x"
    src.mkdir(parents=True)
    (src / "Service.java").write_text(
        "package com.x;\npublic class Service { public void changeEmail() {} }\n",
        encoding="utf-8",
    )
    state: dict[str, Any] = {
        "head_workspace": str(tmp_path),
        "app_dir": "",
        "repo_path": "demo-repo",
        "requirement_text": "change email",
        "use_llm": False,
        "head_ref": "head-v1",
    }
    if job_id is not None:
        state["job_id"] = job_id
    return state


def _run_node_bm25(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> RecordingStore:
    store = RecordingStore()
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)
    monkeypatch.setattr(
        "retrieval.embeddings.EmbeddingClient",
        SimpleNamespace(from_env=lambda: SimpleNamespace(configured=False)),
    )
    from agent.nodes.retrieve_repository_context import (
        retrieve_repository_context_node,
    )

    out = retrieve_repository_context_node(cast(Phase0State, state))
    assert out["retrieval_note"].startswith("Indexed 3 symbol chunks")
    return store


def _run_node_hybrid(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> RecordingStore:
    store = RecordingStore()
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)
    monkeypatch.setattr(
        "retrieval.embeddings.EmbeddingClient",
        SimpleNamespace(from_env=lambda: SimpleNamespace(configured=True)),
    )
    monkeypatch.setattr(
        "retrieval.hybrid.hybrid_search",
        lambda **kwargs: HybridOutcome([], {}),
    )
    from agent.nodes.retrieve_repository_context import (
        retrieve_repository_context_node,
    )

    retrieve_repository_context_node(cast(Phase0State, state))
    return store


# ── node wiring: job_id passed down to the ES index calls ──────────────


def test_node_bm25_path_passes_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _run_node_bm25(_make_state(tmp_path, job_id="job-42"), monkeypatch)
    assert store.calls == [("index_repository", {"job_id": "job-42"})]


def test_node_hybrid_path_passes_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _run_node_hybrid(_make_state(tmp_path, job_id="job-7"), monkeypatch)
    assert store.calls == [("index_with_embeddings", {"job_id": "job-7"})]


def test_node_without_job_id_omits_the_kwarg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _run_node_bm25(_make_state(tmp_path), monkeypatch)
    assert store.calls == [("index_repository", {})]


def test_node_empty_job_id_omits_the_kwarg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _run_node_bm25(_make_state(tmp_path, job_id=""), monkeypatch)
    assert store.calls == [("index_repository", {})]


# ── cleanup_job_projection ───────────────────────────────────────────────


class CleanupSpyStore:
    """Records delete_projection calls and returns scripted deleted counts."""

    def __init__(self, results: list[int]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def delete_projection(
        self, *, tenant_id: str | None = None, job_id: str | None = None
    ) -> int:
        self.calls.append({"tenant_id": tenant_id, "job_id": job_id})
        return self._results.pop(0)

    def close(self) -> None:
        self.closed = True


def test_cleanup_calls_delete_projection_with_the_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = CleanupSpyStore([5])
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: spy)
    assert cleanup_job_projection("job-9") == 5
    assert spy.calls == [{"tenant_id": None, "job_id": "job-9"}]
    assert spy.closed


def test_cleanup_is_idempotent_second_call_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = CleanupSpyStore([5, 0])
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: spy)
    assert cleanup_job_projection("job-9") == 5
    assert cleanup_job_projection("job-9") == 0
    assert len(spy.calls) == 2


def test_cleanup_without_a_job_id_never_touches_es(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom() -> ElasticsearchStore:
        raise AssertionError("no store may be built without a job_id")

    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", _boom)
    assert cleanup_job_projection("") == 0


class FailingStore:
    """Store whose delete_projection raises (ES unreachable)."""

    def delete_projection(self, **kwargs: Any) -> int:
        raise RuntimeError("connection refused")

    def close(self) -> None:
        return None


def test_cleanup_es_unavailable_is_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "storage.elasticsearch.ElasticsearchStore", lambda: FailingStore()
    )
    assert cleanup_job_projection("job-9") == 0


# ── end-to-end through the real store + real delete_projection ───────────


class FakeESDocs:
    """Minimal in-memory ES client: term/bool/match/exists query subset."""

    def __init__(self) -> None:
        self.created = False
        self.docs: list[dict[str, Any]] = []
        self.next_id = 0

    @property
    def indices(self) -> FakeESDocs:
        return self

    def exists(self, index: str) -> bool:
        return self.created

    def create(self, index: str, body: dict[str, Any]) -> None:
        self.created = True

    def delete(self, index: str, ignore_unavailable: bool = False) -> dict[str, Any]:
        self.created = False
        self.docs = []
        return {"acknowledged": True}

    def index(
        self, index: str, document: dict[str, Any], refresh: bool = False
    ) -> dict[str, Any]:
        self.created = True
        self.next_id += 1
        doc_id = str(self.next_id)
        self.docs.append({"_id": doc_id, "_source": document})
        return {"result": "created", "_id": doc_id}

    def bulk(self, operations: list[Any], refresh: bool = False) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        i = 0
        while i < len(operations):
            action = operations[i]
            if "index" in action:
                self.index("x", operations[i + 1])
                items.append({"index": {"status": 201}})
                i += 2
            elif "delete" in action:
                doc_id = action["delete"]["_id"]
                before = len(self.docs)
                self.docs = [d for d in self.docs if d["_id"] != doc_id]
                items.append(
                    {"delete": {"status": 200 if len(self.docs) < before else 404}}
                )
                i += 1
            else:
                i += 1
        return {"errors": False, "items": items}

    @staticmethod
    def _matches(source: dict[str, Any], query: dict[str, Any]) -> bool:
        if "match_all" in query:
            return True
        if "term" in query:
            field, want = next(iter(query["term"].items()))
            return bool(source.get(field) == want)
        if "exists" in query:
            return query["exists"]["field"] in source
        if "match" in query:
            return True
        if "bool" in query:
            bool_query = query["bool"]
            for clause in bool_query.get("must", []):
                if not FakeESDocs._matches(source, clause):
                    return False
            for clause in bool_query.get("must_not", []):
                if FakeESDocs._matches(source, clause):
                    return False
            if "should" in bool_query:
                minimum = bool_query.get("minimum_should_match", 1)
                matched = sum(
                    1
                    for clause in bool_query["should"]
                    if FakeESDocs._matches(source, clause)
                )
                if matched < minimum:
                    return False
            return True
        return False

    def search(
        self,
        index: str,
        body: dict[str, Any],
        ignore_unavailable: bool = False,
    ) -> dict[str, Any]:
        if not self.created:
            return {"hits": {"hits": []}}
        query = body.get("query", {"match_all": {}})
        size = body.get("size", 10)
        matched = [d for d in self.docs if self._matches(d["_source"], query)]
        return {
            "hits": {
                "hits": [
                    {"_id": d["_id"], "_source": d["_source"]}
                    for d in matched[:size]
                ]
            }
        }

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


def _make_store(fake: FakeESDocs) -> ElasticsearchStore:
    store = ElasticsearchStore()
    store._client = fake  # type: ignore[assignment]  # test double
    return store


def test_node_stamps_real_docs_with_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeESDocs()
    monkeypatch.setattr(
        "storage.elasticsearch.ElasticsearchStore", lambda: _make_store(fake)
    )
    monkeypatch.setattr(
        "retrieval.embeddings.EmbeddingClient",
        SimpleNamespace(from_env=lambda: SimpleNamespace(configured=False)),
    )
    from agent.nodes.retrieve_repository_context import (
        retrieve_repository_context_node,
    )

    retrieve_repository_context_node(
        cast(Phase0State, _make_state(tmp_path, job_id="job-42"))
    )
    assert fake.docs
    assert all(d["_source"].get("job_id") == "job-42" for d in fake.docs)


def test_node_without_job_id_indexes_unstamped_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeESDocs()
    monkeypatch.setattr(
        "storage.elasticsearch.ElasticsearchStore", lambda: _make_store(fake)
    )
    monkeypatch.setattr(
        "retrieval.embeddings.EmbeddingClient",
        SimpleNamespace(from_env=lambda: SimpleNamespace(configured=False)),
    )
    from agent.nodes.retrieve_repository_context import (
        retrieve_repository_context_node,
    )

    retrieve_repository_context_node(cast(Phase0State, _make_state(tmp_path)))
    assert fake.docs
    assert all("job_id" not in d["_source"] for d in fake.docs)


def test_cleanup_deletes_stamped_docs_through_real_delete_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeESDocs()
    built: list[ElasticsearchStore] = []

    def _build() -> ElasticsearchStore:
        store = _make_store(fake)
        built.append(store)
        return store

    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", _build)
    seed = _make_store(fake)
    for i in range(3):
        seed.index_code_block(
            "repo:r", "s1", f"F{i}.java", f"m{i}", "void m() {}", job_id="job-9"
        )
    seed.index_code_block("repo:r", "s1", "Other.java", "other", "void o() {}")
    assert len(fake.docs) == 4

    assert cleanup_job_projection("job-9") == 3
    assert len(fake.docs) == 1
    assert "job_id" not in fake.docs[0]["_source"]
    # idempotent: the second call finds nothing and returns 0
    assert cleanup_job_projection("job-9") == 0
    assert len(fake.docs) == 1
    # every store the cleanup entry built was closed again
    assert built and all(s._client is None for s in built)
