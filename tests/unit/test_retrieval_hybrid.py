"""RAG 2.0 hybrid retrieval unit tests — embeddings / rerank / RRF / node wiring.

Fully mocked: no real Elasticsearch, embedding endpoint or LLM gateway is
required. Covers 卷IV 4.1-4.5: index field construction, RRF fusion
ranking, the degradation matrix (embeddings missing → BM25; rerank
unavailable → order preserved with rerank=off), and retrieval metadata.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from agent.repo_graph import RepoGraph
from retrieval.embeddings import EmbeddingClient
from retrieval.hybrid import HybridOutcome, hybrid_search, rrf_fuse
from retrieval.rerank import RerankResult, rerank
from storage.elasticsearch import ElasticsearchConfig, ElasticsearchStore

FILES = {
    "com/specproof/demo/service/UserService.java": """package com.specproof.demo.service;

@Service
public class UserService {

    @Transactional
    public UserResponse changeEmail(Long userId, ChangeEmailRequest request) {
        invalidateOldTokens(userId);
        return new UserResponse(userId, "u", "e");
    }

    private void invalidateOldTokens(Long userId) {
        redisTemplate.delete("token:user:" + userId);
    }

    public UserResponse getUser(Long id) {
        return new UserResponse(id, "u", "e");
    }
}
""",
}


def _hit(path: str, symbol: str, content: str = "x") -> dict[str, Any]:
    return {"path": path, "symbol": symbol, "content": content}


class FakeEmbedder:
    def __init__(
        self,
        configured: bool = True,
        vectors: list[list[float]] | None = None,
        reason: str = "",
        model: str = "test-embed-model",
    ) -> None:
        self.configured = configured
        self.model = model
        self._vectors = vectors
        self._reason = reason

    def embed(self, texts: list[str]) -> tuple[list[list[float]] | None, str]:
        if self._vectors is None and not self._reason:
            return ([[0.1, 0.2] for _ in texts], "")
        return (self._vectors, self._reason)


class FakeES:
    """ES-like store for hybrid_search: configurable BM25 / vector hits."""

    def __init__(
        self, bm25: list[dict[str, Any]], vectors: list[dict[str, Any]] | None = None
    ) -> None:
        self._bm25 = bm25
        self._vectors = list(vectors) if vectors is not None else []

    def search_code(self, repo, query, commit_sha=None, size=20):
        return [dict(d) for d in self._bm25[:size]]

    def vector_search(self, repo, query_vector, k=10, commit_sha=None):
        return [dict(d) for d in self._vectors[:k]]


@pytest.fixture()
def no_rerank(monkeypatch):
    """Pin hybrid_search's rerank stage to honest passthrough."""

    def off(query, candidates, **kwargs):
        return RerankResult(
            mode="off", order=list(range(len(candidates))), reason="off (test)"
        )

    monkeypatch.setattr("retrieval.hybrid.rerank", off)


# ── RRF fusion ────────────────────────────────────────────────────────────


def test_rrf_formula_exact():
    bm25 = [_hit("a.java", "A"), _hit("b.java", "B")]
    vectors = [_hit("b.java", "B"), _hit("c.java", "C")]
    fused = rrf_fuse(bm25, vectors, k=60)
    assert [h["symbol"] for h in fused] == ["B", "A", "C"]
    assert fused[0]["rrf_score"] == pytest.approx(1 / 61 + 1 / 60)
    assert fused[1]["rrf_score"] == pytest.approx(1 / 60)
    assert fused[2]["rrf_score"] == pytest.approx(1 / 61)
    assert fused[0]["source"] == "bm25+vector"
    assert fused[1]["source"] == "bm25"
    assert fused[2]["source"] == "vector"
    assert fused[0]["bm25_rank"] == 1
    assert fused[0]["vector_rank"] == 0


def test_hybrid_fusion_ranking_constructed(no_rerank):
    # BM25 prefers A, but the vector channel lifts C; the fused order must
    # reflect both lists, not the BM25 order alone.
    bm25 = [
        _hit("a.java", "A"),
        _hit("b.java", "B"),
        _hit("c.java", "C"),
        _hit("d.java", "D"),
    ]
    vectors = [_hit("c.java", "C")]
    outcome = hybrid_search(
        FakeES(bm25, vectors),
        "q",
        "repo:x",
        k=16,
        embedder=FakeEmbedder(),
        graph=None,
    )
    assert [h["symbol"] for h in outcome.results] == ["C", "A", "B", "D"]
    assert outcome.meta["mode"] == "hybrid"
    assert outcome.meta["embedding_used"] == "test-embed-model"
    assert outcome.meta["bm25_hits"] == 4
    assert outcome.meta["vector_hits"] == 1


# ── degradation matrix (卷IV 4.3) ─────────────────────────────────────────


def test_degrade_no_embedder_is_bm25_only():
    outcome = hybrid_search(
        FakeES([_hit("a.java", "A"), _hit("b.java", "B")]),
        "q",
        "repo:x",
        k=16,
        embedder=None,
        graph=None,
    )
    assert outcome.meta["mode"] == "bm25"
    assert outcome.meta["vector_hits"] == 0
    assert outcome.meta["rerank_mode"] == "off"
    assert outcome.meta["embedding_used"] is None
    assert [h["symbol"] for h in outcome.results] == ["A", "B"]


def test_degrade_unconfigured_embedder_is_bm25_only():
    outcome = hybrid_search(
        FakeES([_hit("a.java", "A")]),
        "q",
        "repo:x",
        k=16,
        embedder=FakeEmbedder(configured=False, reason="no endpoint"),
        graph=None,
    )
    assert outcome.meta["mode"] == "bm25"
    assert outcome.meta["embedding_used"] is None
    assert outcome.meta["embedding_error"] is None  # not even attempted


def test_degrade_embedding_failure_falls_back_bm25():
    outcome = hybrid_search(
        FakeES([_hit("a.java", "A")]),
        "q",
        "repo:x",
        k=16,
        embedder=FakeEmbedder(reason="gateway down"),
        graph=None,
    )
    assert outcome.meta["mode"] == "bm25"
    assert outcome.meta["embedding_error"] == "gateway down"
    assert outcome.meta["embedding_used"] is None


def test_degrade_empty_vector_results_falls_back_bm25():
    outcome = hybrid_search(
        FakeES([_hit("a.java", "A")], vectors=[]),
        "q",
        "repo:x",
        k=16,
        embedder=FakeEmbedder(),
        graph=None,
    )
    assert outcome.meta["mode"] == "bm25"
    assert outcome.meta["vector_hits"] == 0
    assert outcome.meta["embedding_used"] == "test-embed-model"


def test_rerank_unavailable_preserves_order(no_rerank):
    outcome = hybrid_search(
        FakeES([_hit("a.java", "A"), _hit("b.java", "B")], vectors=[_hit("a.java", "A")]),
        "q",
        "repo:x",
        k=16,
        embedder=FakeEmbedder(),
        graph=None,
    )
    assert outcome.meta["rerank_mode"] == "off"
    assert [h["symbol"] for h in outcome.results] == ["A", "B"]


def test_rerank_reorders_results(monkeypatch):
    def llm_rerank(query, candidates, **kwargs):
        return RerankResult(mode="llm", order=list(reversed(range(len(candidates)))))

    monkeypatch.setattr("retrieval.hybrid.rerank", llm_rerank)
    outcome = hybrid_search(
        FakeES([_hit("a.java", "A"), _hit("b.java", "B")], vectors=[_hit("a.java", "A")]),
        "q",
        "repo:x",
        k=16,
        embedder=FakeEmbedder(),
        graph=None,
    )
    assert outcome.meta["rerank_mode"] == "llm"
    assert [h["symbol"] for h in outcome.results] == ["B", "A"]


def test_graph_expansion_appends_neighborhood():
    outcome = hybrid_search(
        FakeES([_hit("com/specproof/demo/service/UserService.java", "changeEmail")]),
        "changeEmail",
        "repo:x",
        k=16,
        embedder=None,
        graph=RepoGraph(FILES),
    )
    symbols = {h["symbol"] for h in outcome.results}
    assert "changeEmail" in symbols
    assert "invalidateOldTokens" in symbols
    assert "getUser" in symbols
    assert any(h.get("source") == "symbol_graph" for h in outcome.results)
    assert outcome.meta["expanded"] >= 2
    assert outcome.meta["hops"] == 2


def test_budget_truncation_and_metadata(no_rerank):
    outcome = hybrid_search(
        FakeES(
            [_hit("a.java", "A"), _hit("b.java", "B"), _hit("c.java", "C")],
            vectors=[_hit("c.java", "C")],
        ),
        "q",
        "repo:x",
        k=2,
        embedder=FakeEmbedder(),
        graph=None,
    )
    assert len(outcome.results) == 2
    assert outcome.meta["truncated"] is True
    assert outcome.meta["returned"] == 2
    for required in ("bm25_hits", "vector_hits", "rerank_mode", "embedding_used"):
        assert required in outcome.meta
    assert outcome.results[0]["rank"] == 0
    assert outcome.results[1]["rank"] == 1


# ── EmbeddingClient ───────────────────────────────────────────────────────


def test_embed_batches_bounded_by_64():
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        batch = payload["input"]
        batches.append(batch)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [0.1, 0.2]} for i in range(len(batch))
                ]
            },
        )

    client = EmbeddingClient(
        base_url="http://emb", api_key="k", model="m",
        transport=httpx.MockTransport(handler),
    )
    vectors, reason = client.embed([f"t{i}" for i in range(130)])
    assert reason == ""
    assert vectors is not None
    assert len(vectors) == 130
    assert [len(b) for b in batches] == [64, 64, 2]
    for batch in batches:
        assert len(batch) <= 64


def test_embed_429_retries_honoring_retry_after():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0.01"})
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}
        )

    client = EmbeddingClient(
        base_url="http://emb", api_key="k", model="m", max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    vectors, reason = client.embed(["hello"])
    assert vectors == [[1.0, 2.0]]
    assert reason == ""
    assert attempts["n"] == 2


def test_embed_401_is_not_retried_and_reasoned():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    client = EmbeddingClient(
        base_url="http://emb", api_key="k", model="m", max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    vectors, reason = client.embed(["x"])
    assert vectors is None
    assert "401" in reason
    assert attempts["n"] == 1


def test_embed_never_fabricates_when_endpoint_dies():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    client = EmbeddingClient(
        base_url="http://emb", api_key="k", model="m", max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    vectors, reason = client.embed(["x"])
    assert vectors is None
    assert "503" in reason


def test_embed_malformed_response_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    client = EmbeddingClient(
        base_url="http://emb", api_key="k", model="m",
        transport=httpx.MockTransport(handler),
    )
    vectors, reason = client.embed(["x"])
    assert vectors is None
    assert "data" in reason


def test_embed_rejects_inconsistent_dims():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        batch = payload["input"]
        dims = 3 if len(batch) == 2 else 4
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [0.1] * dims} for i in range(len(batch))
                ]
            },
        )

    client = EmbeddingClient(
        base_url="http://emb", api_key="k", model="m", batch_size=2,
        transport=httpx.MockTransport(handler),
    )
    vectors, reason = client.embed(["a", "b", "c"])
    assert vectors is None
    assert "inconsistent" in reason


_EMBEDDING_ENV = (
    "LLM_EMBEDDING_BASE_URL",
    "LLM_EMBEDDING_API_KEY",
    "LLM_EMBEDDING_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
)


@pytest.fixture()
def clear_embedding_env(monkeypatch):
    for name in _EMBEDDING_ENV:
        monkeypatch.delenv(name, raising=False)


def test_from_env_prefers_embedding_vars(clear_embedding_env, monkeypatch):
    monkeypatch.setenv("LLM_EMBEDDING_BASE_URL", "http://emb/v1")
    monkeypatch.setenv("LLM_EMBEDDING_API_KEY", "emb-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "emb-model")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_MODEL", "chat-model")
    client = EmbeddingClient.from_env()
    assert client.configured
    assert client.base_url == "http://emb/v1"
    assert client.api_key == "emb-key"
    assert client.model == "emb-model"


def test_from_env_falls_back_to_llm_vars(clear_embedding_env, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_MODEL", "chat-model")
    client = EmbeddingClient.from_env()
    assert client.configured
    assert client.base_url == "http://llm/v1"
    assert client.model == "chat-model"


def test_from_env_unconfigured_with_reason(clear_embedding_env):
    client = EmbeddingClient.from_env()
    assert not client.configured
    assert "LLM_EMBEDDING_BASE_URL" in client.config_reason


def test_from_env_placeholder_key_is_unconfigured(clear_embedding_env, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("LLM_API_KEY", "replace_me")
    client = EmbeddingClient.from_env()
    assert not client.configured
    assert "replace_me" in client.config_reason


def test_embed_unconfigured_returns_none_and_reason(clear_embedding_env):
    client = EmbeddingClient.from_env()
    vectors, reason = client.embed(["x"])
    assert vectors is None
    assert client.config_reason == reason


# ── rerank tiers ──────────────────────────────────────────────────────────


class _FakeCrossEncoder:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return list(self._scores)


class _FakeProvider:
    def __init__(self, content: str) -> None:
        self._content = content

    async def chat(self, messages, **kwargs):
        return SimpleNamespace(content=self._content)


def test_rerank_cross_encoder_tier(monkeypatch):
    monkeypatch.setenv("RERANK_MODEL", "bge-reranker-base")
    monkeypatch.setattr(
        "retrieval.rerank._load_cross_encoder",
        lambda name: _FakeCrossEncoder([0.1, 0.9, 0.5]),
    )
    result = rerank("q", [_hit("a", "A"), _hit("b", "B"), _hit("c", "C")])
    assert result.mode == "cross_encoder"
    assert result.order == [1, 2, 0]
    assert result.scores == [0.1, 0.9, 0.5]


def test_rerank_llm_tier(monkeypatch):
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    candidates = [_hit("a", "A"), _hit("b", "B"), _hit("c", "C")]
    result = rerank("q", candidates, provider=_FakeProvider("[2, 0, 1]"))
    assert result.mode == "llm"
    assert result.order == [2, 0, 1]


def test_rerank_llm_invalid_output_falls_back_off(monkeypatch):
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    candidates = [_hit("a", "A"), _hit("b", "B"), _hit("c", "C")]
    result = rerank("q", candidates, provider=_FakeProvider("[0, 1]"))
    assert result.mode == "off"
    assert result.order == [0, 1, 2]
    assert result.reason and "LLM" in result.reason


def test_rerank_llm_garbage_falls_back_off(monkeypatch):
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    result = rerank(
        "q", [_hit("a", "A"), _hit("b", "B")], provider=_FakeProvider("not json")
    )
    assert result.mode == "off"
    assert result.order == [0, 1]


def test_rerank_llm_budget_caps_input_and_appends_tail(monkeypatch):
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    candidates = [_hit(f"f{i}.java", f"S{i}") for i in range(5)]
    result = rerank(
        "q", candidates, provider=_FakeProvider("[2, 0, 1]"), max_candidates=3,
    )
    assert result.mode == "llm"
    assert result.order == [2, 0, 1, 3, 4]


def test_rerank_use_llm_false_skips_llm(monkeypatch):
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    result = rerank(
        "q",
        [_hit("a", "A"), _hit("b", "B")],
        provider=_FakeProvider("[1, 0]"),
        use_llm=False,
    )
    assert result.mode == "off"
    assert result.order == [0, 1]
    assert result.reason == "no reranker configured"


def test_rerank_cross_encoder_unavailable_falls_to_llm(monkeypatch):
    monkeypatch.setenv("RERANK_MODEL", "missing-model")
    monkeypatch.setattr("retrieval.rerank._load_cross_encoder", lambda name: None)
    candidates = [_hit("a", "A"), _hit("b", "B"), _hit("c", "C")]
    result = rerank("q", candidates, provider=_FakeProvider("[2, 1, 0]"))
    assert result.mode == "llm"
    assert result.order == [2, 1, 0]


def test_rerank_off_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = rerank("q", [_hit("a", "A"), _hit("b", "B")])
    assert result.mode == "off"
    assert result.order == [0, 1]
    assert result.reason == "no LLM gateway configured"


def test_rerank_single_candidate_is_off():
    result = rerank("q", [_hit("a", "A")])
    assert result.mode == "off"
    assert result.order == [0]


# ── storage index field construction ──────────────────────────────────────


class FakeESClient:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None
        self.docs: list[dict[str, Any]] = []
        self.bodies: list[dict[str, Any]] = []
        self.search_result: dict[str, Any] = {"hits": {"hits": []}}

    def ping(self) -> bool:
        return True

    @property
    def indices(self) -> FakeESClient:
        return self

    def exists(self, index: str) -> bool:
        return False

    def create(self, index: str, body: dict) -> None:
        self.created = body

    def delete(self, index: str, ignore_unavailable: bool = False) -> None:
        pass

    def index(self, index: str, document: dict, refresh: bool = False) -> None:
        self.docs.append(dict(document))

    def bulk(self, operations: list, refresh: bool = False) -> dict:
        for i in range(0, len(operations), 2):
            if i + 1 < len(operations):
                self.docs.append(dict(operations[i + 1]))
        return {"errors": False}

    def search(self, index: str, body: dict) -> dict:
        self.bodies.append(body)
        return self.search_result

    def count(self, index: str, body: dict) -> dict:
        return {"count": len(self.docs)}

    def close(self) -> None:
        pass


@pytest.fixture()
def index_store(monkeypatch):
    fake = FakeESClient()
    store = ElasticsearchStore(config=ElasticsearchConfig(vector_dims=4))
    monkeypatch.setattr(ElasticsearchStore, "client", property(lambda self: fake))
    return store, fake


def test_ensure_indices_enables_hnsw_vector_field(index_store):
    store, fake = index_store
    store.ensure_indices()
    props = fake.created["mappings"]["properties"]["embedding"]
    assert props["type"] == "dense_vector"
    assert props["dims"] == 4
    assert props["index"] is True
    assert props["similarity"] == "cosine"
    assert props["index_options"] == {"type": "hnsw", "m": 16, "ef_construction": 100}


def test_vector_dims_configurable_from_env(monkeypatch):
    monkeypatch.setenv("ES_VECTOR_DIMS", "1024")
    assert ElasticsearchConfig.from_env().vector_dims == 1024
    monkeypatch.setenv("ES_VECTOR_DIMS", "garbage")
    assert ElasticsearchConfig.from_env().vector_dims == 1536


def test_index_code_block_carries_optional_embedding(index_store):
    store, fake = index_store
    store.index_code_block(
        "repo:x", "s1", "a.java", "A", "body", embedding=[0.1, 0.2, 0.3, 0.4]
    )
    assert fake.docs[-1]["embedding"] == [0.1, 0.2, 0.3, 0.4]
    store.index_code_block("repo:x", "s1", "b.java", "B", "body")
    assert "embedding" not in fake.docs[-1]


def test_index_repository_omits_embedding_field(index_store):
    store, fake = index_store
    store.index_repository("repo:x", "s1", {"a.java": "class A { public void m() {} }"})
    assert fake.docs
    assert all("embedding" not in doc for doc in fake.docs)


def test_index_with_embeddings_attaches_vectors(index_store):
    store, fake = index_store
    files = {"a.java": "class A { public void m() {} }", "b.java": "class B {}"}
    embedder = FakeEmbedder(vectors=[[0.1] * 4, [0.2] * 4])
    report = store.index_with_embeddings("repo:x", "s1", files, embedder)
    assert report["indexed"] == 2
    assert report["embedded"] == 2
    assert report["vectors_skipped"] == 0
    assert all(len(doc["embedding"]) == 4 for doc in fake.docs)


def test_index_with_embeddings_unavailable_degrades_bm25_only(index_store):
    store, fake = index_store
    embedder = FakeEmbedder(reason="endpoint down")
    report = store.index_with_embeddings(
        "repo:x", "s1", {"a.java": "class A { public void m() {} }"}, embedder,
    )
    assert report["indexed"] == 1
    assert report["embedded"] == 0
    assert any("endpoint down" in note for note in report["embedding_notes"])
    assert all("embedding" not in doc for doc in fake.docs)


def test_index_with_embeddings_dims_mismatch_skips_vectors(index_store):
    store, fake = index_store
    embedder = FakeEmbedder(vectors=[[0.1] * 3])
    report = store.index_with_embeddings(
        "repo:x", "s1", {"a.java": "class A { public void m() {} }"}, embedder,
    )
    assert report["indexed"] == 1
    assert report["embedded"] == 0
    assert report["vectors_skipped"] == 1
    assert "embedding" not in fake.docs[0]


def test_vector_search_builds_knn_body(index_store):
    store, fake = index_store
    hits = store.vector_search("repo:x", [0.1, 0.2, 0.3, 0.4], k=5)
    assert hits == []
    knn = fake.bodies[-1]["knn"]
    assert knn["field"] == "embedding"
    assert knn["query_vector"] == [0.1, 0.2, 0.3, 0.4]
    assert knn["k"] == 5
    assert knn["num_candidates"] == 25
    assert knn["filter"] == {"term": {"repo": "repo:x"}}
    assert fake.bodies[-1]["size"] == 5


def test_vector_search_attaches_vector_score(index_store):
    store, fake = index_store
    fake.search_result = {
        "hits": {"hits": [{"_source": {"path": "a.java", "symbol": "A"}, "_score": 0.93}]}
    }
    hits = store.vector_search("repo:x", [0.1] * 4)
    assert hits[0]["vector_score"] == pytest.approx(0.93)
    assert hits[0]["symbol"] == "A"


def test_search_code_passes_size(index_store):
    store, fake = index_store
    store.search_code("repo:x", "query", size=7)
    assert fake.bodies[-1]["size"] == 7
    assert fake.bodies[-1]["query"]["bool"]["must"][0] == {"term": {"repo": "repo:x"}}


# ── node wiring ───────────────────────────────────────────────────────────


class FakeStore:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready
        self.calls: list[tuple] = []

    def is_ready(self) -> bool:
        return self.ready

    def index_repository(self, repo, commit_sha, files):
        self.calls.append(("index_repository", repo))
        return 3

    def search_code(self, repo, query, commit_sha=None, size=20):
        return [_hit("com/x/Service.java", "changeEmail", "public void changeEmail() {}")]

    def index_with_embeddings(self, repo, commit_sha, files, embedder):
        self.calls.append(("index_with_embeddings", repo))
        return {"indexed": 3, "embedded": 3, "vectors_skipped": 0, "embedding_notes": []}


def _make_state(tmp_path) -> dict[str, Any]:
    src = tmp_path / "src" / "main" / "java" / "com" / "x"
    src.mkdir(parents=True)
    (src / "Service.java").write_text(
        "package com.x;\npublic class Service { public void changeEmail() {} }\n",
        encoding="utf-8",
    )
    return {
        "head_workspace": str(tmp_path),
        "app_dir": "",
        "repo_path": "demo-repo",
        "requirement_text": "change email",
        "use_llm": False,
        "head_ref": "head-v1",
    }


def _patch_node(monkeypatch, store: FakeStore) -> None:
    monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)


def test_node_bm25_path_without_embeddings(tmp_path, monkeypatch):
    store = FakeStore()
    _patch_node(monkeypatch, store)
    unconfigured = SimpleNamespace(configured=False, config_reason="no endpoint")
    monkeypatch.setattr(
        "retrieval.embeddings.EmbeddingClient",
        SimpleNamespace(from_env=lambda: unconfigured),
    )
    called = {"hybrid": False}

    def fake_hybrid(**kwargs):
        called["hybrid"] = True
        return HybridOutcome([], {})

    monkeypatch.setattr("retrieval.hybrid.hybrid_search", fake_hybrid)

    from agent.nodes.retrieve_repository_context import retrieve_repository_context_node

    out = retrieve_repository_context_node(_make_state(tmp_path))
    assert not called["hybrid"]
    assert store.calls == [("index_repository", "repo:demo-repo")]
    assert out["repo_context"]
    assert out["repo_context"][0]["source"] == "bm25"
    assert out["retrieval_note"].startswith("Indexed 3 symbol chunks")


def test_node_hybrid_path_with_embeddings(tmp_path, monkeypatch):
    store = FakeStore()
    _patch_node(monkeypatch, store)
    configured = SimpleNamespace(configured=True, config_reason="")
    monkeypatch.setattr(
        "retrieval.embeddings.EmbeddingClient",
        SimpleNamespace(from_env=lambda: configured),
    )
    results = [_hit("com/x/Service.java", "changeEmail", "void m() {}")]
    results[0].update({"source": "bm25+vector", "rank": 0, "rrf_score": 2 / 61})
    meta = {
        "mode": "hybrid",
        "embedding_used": "text-embed-3",
        "embedding_error": None,
        "bm25_hits": 1,
        "vector_hits": 1,
        "rerank_mode": "off",
        "rerank_reason": None,
    }

    def fake_hybrid(**kwargs):
        return HybridOutcome(results, meta)

    monkeypatch.setattr("retrieval.hybrid.hybrid_search", fake_hybrid)

    from agent.nodes.retrieve_repository_context import retrieve_repository_context_node

    out = retrieve_repository_context_node(_make_state(tmp_path))
    assert store.calls == [("index_with_embeddings", "repo:demo-repo")]
    note = out["retrieval_note"]
    assert "hybrid_rrf" in note
    assert "bm25_hits=1" in note
    assert "vector_hits=1" in note
    assert "rerank=off" in note
    assert "embedding=text-embed-3" in note
    assert out["repo_context"][0]["source"] == "bm25+vector"
    assert out["repo_context"][0]["rrf_score"] == pytest.approx(2 / 61)


def test_node_es_unavailable_returns_honest_note(tmp_path, monkeypatch):
    _patch_node(monkeypatch, FakeStore(ready=False))

    from agent.nodes.retrieve_repository_context import retrieve_repository_context_node

    out = retrieve_repository_context_node(_make_state(tmp_path))
    assert out["repo_context"] == []
    assert "unavailable" in out["retrieval_note"]
