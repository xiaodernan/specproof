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
    millisecond ladder (first-use-wins; top bucket 36s clears the client's
    request_timeout=30 by 1.2x — the ladder case below anchors this).
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


def test_es_bucket_ladder_clears_the_request_timeout() -> None:
    """§8.10 "ES 延迟" (#213): the ladder's top STRICTLY exceeds the
    client's own request_timeout, read from the ``Elasticsearch(...)``
    construction's keyword by AST — not by a text regex, which would bind
    the bucket comment (a text occurrence that precedes the construction)
    instead of the producer. An equal top pushes a request cut off AT the
    timeout (measured slightly over it) into +Inf, falsifying the
    "timeout cuts stay finite" claim.
    """
    import ast
    from pathlib import Path

    from storage.elasticsearch import _ES_BUCKETS

    assert list(_ES_BUCKETS) == sorted(_ES_BUCKETS)
    assert all(b > 0 for b in _ES_BUCKETS)

    source = Path(__file__).resolve().parents[2] / "storage" / "elasticsearch.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    constructions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Elasticsearch"
    ]
    assert len(constructions) == 1, (
        f"expected one Elasticsearch construction, got {len(constructions)}"
    )
    request_timeouts = [
        kw.value
        for kw in constructions[0].keywords
        if kw.arg == "request_timeout"
    ]
    assert len(request_timeouts) == 1, "client request_timeout keyword not found"
    value = request_timeouts[0]
    assert isinstance(value, ast.Constant) and isinstance(value.value, (int, float))
    assert _ES_BUCKETS[-1] > float(value.value), (
        f"ladder top {_ES_BUCKETS[-1]}s does not clear request_timeout "
        f"{value.value}s — a request cut off at the timeout would land in +Inf"
    )
