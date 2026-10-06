"""P2 unit tests — Elasticsearch repository indexing (mock client)."""

import pytest

from storage.elasticsearch import ElasticsearchStore


class FakeES:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.deleted = 0

    def ping(self) -> bool:
        return True

    @property
    def indices(self) -> "FakeES":
        return self

    def exists(self, index: str) -> bool:  # noqa: ARG002
        return True

    def create(self, index: str, body: dict) -> None:  # noqa: ARG002
        pass

    def index(self, index: str, document: dict, refresh: bool = False) -> None:  # noqa: ARG002
        self.docs.append(document)

    def bulk(self, operations: list, refresh: bool = False) -> dict:
        # operations alternate: {"index": {...}}, {doc}, {"index": {...}}, ...
        for i in range(0, len(operations), 2):
            if i + 1 < len(operations):
                self.docs.append(operations[i + 1])
        return {"errors": False}

    def delete(self, index: str, ignore_unavailable: bool = False) -> None:  # noqa: ARG002
        self.deleted += 1
        self.docs = []

    def count(self, index: str, body: dict) -> dict:  # noqa: ARG002
        return {"count": len(self.docs)}

    def search(self, index: str, body: dict) -> dict:  # noqa: ARG002
        return {"hits": {"hits": [{"_source": d} for d in self.docs[:3]]}}

    def close(self) -> None:
        pass


@pytest.fixture()
def store(monkeypatch) -> ElasticsearchStore:
    fake = FakeES()
    es_store = ElasticsearchStore()
    monkeypatch.setattr(
        ElasticsearchStore, "client", property(lambda self: fake)  # type: ignore[arg-type]
    )
    return es_store


def test_index_repository_symbol_chunks(store):
    files = {
        "com/specproof/demo/controller/UserController.java": (
            "@RestController\npublic class UserController {\n"
            "  @GetMapping(\"/x\")\n  public String x() { return \"x\"; }\n}"
        ),
        "README.md": "# policy\n- Must keep endpoints authenticated.\n",
    }
    count = store.index_repository("repo:test", "abc123", files)
    assert count >= 2  # method chunks + readme chunk
    assert store.count_repo_docs("repo:test") == count


def test_reindex_is_idempotent(store):
    files = {"a.java": "class A { public void m() {} }"}
    first = store.index_repository("repo:test", "s1", files)
    second = store.index_repository("repo:test", "s2", files)
    assert second == first  # delete-by-query + re-index yields same count


def test_search_returns_sources(store):
    files = {"a.java": "class A { public void m() {} }"}
    store.index_repository("repo:test", "s1", files)
    hits = store.search_code("repo:test", "void m")
    assert isinstance(hits, list)


def test_es_requests_are_timed_per_op(store):
    """§8.10 "ES 延迟" (#169): every store method's ES round trip lands in
    its per-op ``es_request_seconds_*`` histogram, pinned to the custom
    millisecond ladder (first-use-wins; top bucket 30s equals the client's
    request_timeout, so even a timed-out request stays in a finite bucket).
    """
    from observability import metrics as metrics_module
    from storage.elasticsearch import _ES_BUCKETS

    before = metrics_module.snapshot()["histograms"]

    def count_of(hists: dict, op: str) -> float:
        return hists.get(f"es_request_seconds_{op}", {}).get("count", 0.0)

    files = {"a.java": "class A { public void m() {} }"}
    store.index_repository("repo:test", "s1", files)  # bulk
    store.search_code("repo:test", "void m")          # search
    store.count_repo_docs("repo:test")                # indices (exists) + count
    assert store.is_ready() is True                   # ping

    after = metrics_module.snapshot()["histograms"]

    # indices x4: index_repository's ensure_indices, delete_repo's
    # indices.delete + its re-ensure, count_repo_docs' exists guard.
    for op, expected_calls in (
        ("bulk", 1), ("search", 1), ("count", 1),
        ("indices", 4), ("ping", 1),
    ):
        hist = after[f"es_request_seconds_{op}"]
        assert hist["bounds"] == list(_ES_BUCKETS), f"op {op} ladder drifted"
        assert hist["count"] - count_of(before, op) == expected_calls
