"""Backlog #10 — ES projection deletion cleanup (all offline, fake client).

Covers:
- optional job_id stamping on every write path (index_code_block /
  index_repository / index_with_embeddings) without changing the
  existing no-job-id document shape;
- the tenant/repo/job cleanup filter (build_tenant_repo_filter with
  job_id), including the default-tenant legacy-unstamped clause;
- delete_projection / count_projection_docs by job_id and/or tenant_id:
  per-document deletion (delete_by_query is never used — it hard-crashes
  on Windows in elasticsearch-py 8.19.x), idempotent, missing index and
  missing documents are no-ops, and a selector argument is required.

The fake Elasticsearch client implements an in-memory document store with
exactly the term/bool/exists query subset the cleanup filter uses.
No real Elasticsearch, no network.
"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.events import DEFAULT_TENANT_ID
from storage.elasticsearch import (
    _DELETE_PAGE_SIZE,
    ElasticsearchConfig,
    ElasticsearchStore,
    build_tenant_repo_filter,
)


class FakeESProjection:
    """In-memory ES fake: _id-addressed docs + term/bool/exists matching."""

    def __init__(self) -> None:
        self.created = False
        self.mapping: dict[str, Any] = {}
        self.docs: list[dict[str, Any]] = []  # {"_id": str, "_source": dict}
        self.next_id = 0
        self.search_bodies: list[dict[str, Any]] = []
        self.delete_batches: list[list[str]] = []

    @property
    def indices(self) -> FakeESProjection:
        return self

    def exists(self, index: str) -> bool:
        return self.created

    def create(self, index: str, body: dict[str, Any]) -> None:
        self.created = True
        self.mapping = body

    def delete(self, index: str, ignore_unavailable: bool = False) -> dict[str, Any]:
        self.created = False
        self.docs = []
        return {"acknowledged": True}

    def index(
        self, index: str, document: dict[str, Any], refresh: bool = False
    ) -> dict[str, Any]:
        self.created = True
        return self._add(document)

    def _add(self, source: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        doc_id = str(self.next_id)
        self.docs.append({"_id": doc_id, "_source": source})
        return {"result": "created", "_id": doc_id}

    def bulk(
        self, operations: list[Any], refresh: bool = False
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        deleted_ids: list[str] = []
        i = 0
        while i < len(operations):
            action = operations[i]
            if "index" in action:
                self._add(operations[i + 1])
                items.append({"index": {"status": 201}})
                i += 2
            elif "delete" in action:
                doc_id = action["delete"]["_id"]
                remaining = [d for d in self.docs if d["_id"] != doc_id]
                if len(remaining) < len(self.docs):
                    self.docs = remaining
                    deleted_ids.append(doc_id)
                    items.append({"delete": {"status": 200}})
                else:
                    items.append({"delete": {"status": 404}})
                i += 1
            else:
                i += 1
        if deleted_ids:
            self.delete_batches.append(deleted_ids)
        return {"errors": False, "items": items}

    @staticmethod
    def _matches(source: dict[str, Any], query: dict[str, Any]) -> bool:
        if "match_all" in query:
            return True
        if "term" in query:
            field, want = next(iter(query["term"].items()))
            return source.get(field) == want
        if "bool" in query:
            bool_query = query["bool"]
            for clause in bool_query.get("must", []):
                if not FakeESProjection._matches(source, clause):
                    return False
            for clause in bool_query.get("must_not", []):
                if FakeESProjection._matches(source, clause):
                    return False
            if "should" in bool_query:
                minimum = bool_query.get("minimum_should_match", 1)
                matched = sum(
                    1
                    for clause in bool_query["should"]
                    if FakeESProjection._matches(source, clause)
                )
                if matched < minimum:
                    return False
            return True
        if "exists" in query:
            return query["exists"]["field"] in source
        return False

    def search(
        self,
        index: str,
        body: dict[str, Any],
        ignore_unavailable: bool = False,
    ) -> dict[str, Any]:
        self.search_bodies.append(body)
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

    def count(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.created:
            return {"count": 0}
        query = body.get("query", {"match_all": {}})
        return {
            "count": sum(
                1 for d in self.docs if self._matches(d["_source"], query)
            )
        }

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


class FakeEmbedder:
    """EmbeddingClient stand-in: dims-correct vectors, no failures."""

    def embed(self, texts: list[str]) -> tuple[list[list[float]] | None, str | None]:
        return [[0.0] * 4 for _ in texts], None


def make_store(fake: FakeESProjection) -> ElasticsearchStore:
    store = ElasticsearchStore()
    store._client = fake  # type: ignore[assignment]  # test double
    return store


@pytest.fixture()
def es() -> tuple[ElasticsearchStore, FakeESProjection]:
    fake = FakeESProjection()
    fake.created = True
    return make_store(fake), fake


def seed(
    store: ElasticsearchStore,
    tenant: str,
    job: str,
    count: int = 1,
) -> None:
    for i in range(count):
        store.index_code_block(
            "repo:r",
            "s1",
            f"F{i}.java",
            f"m{i}",
            "void m() {}",
            tenant_id=tenant,
            job_id=job,
        )


# ── job_id stamping on the write paths ────────────────────────────────────


def test_index_code_block_stamps_job_id_only_when_given(es) -> None:
    store, fake = es
    store.index_code_block(
        "repo:x", "s1", "A.java", "m", "void m() {}", job_id="job-1"
    )
    assert fake.docs[0]["_source"]["job_id"] == "job-1"
    store.index_code_block("repo:x", "s1", "B.java", "n", "void n() {}")
    assert "job_id" not in fake.docs[1]["_source"]


def test_index_repository_stamps_job_id_and_keeps_default_shape(es) -> None:
    store, fake = es
    count = store.index_repository(
        "repo:x",
        "s1",
        {"a.java": "class A { public void m() {} }"},
        job_id="job-9",
    )
    assert count >= 1
    assert fake.docs
    assert all(d["_source"]["job_id"] == "job-9" for d in fake.docs)
    # without job_id the pre-#10 document shape is unchanged
    store.index_repository("repo:y", "s1", {"b.java": "class B {}"})
    assert all(
        "job_id" not in d["_source"]
        for d in fake.docs
        if d["_source"]["repo"] == "repo:y"
    )


def test_index_with_embeddings_stamps_job_id() -> None:
    fake = FakeESProjection()
    fake.created = True
    store = ElasticsearchStore(config=ElasticsearchConfig(vector_dims=4))
    store._client = fake  # type: ignore[assignment]  # test double
    report = store.index_with_embeddings(
        "repo:x",
        "s1",
        {"a.java": "class A { public void m() {} }"},
        FakeEmbedder(),
        job_id="job-3",
    )
    assert report["indexed"] >= 1
    assert report["embedded"] == report["indexed"]
    assert fake.docs
    assert all(d["_source"]["job_id"] == "job-3" for d in fake.docs)


def test_ensure_indices_maps_job_id_as_keyword() -> None:
    fake = FakeESProjection()
    store = make_store(fake)
    store.ensure_indices()
    assert fake.mapping["mappings"]["properties"]["job_id"] == {"type": "keyword"}


# ── cleanup filter with job_id ─────────────────────────────────────────────


def test_job_only_filter_is_a_plain_term() -> None:
    assert build_tenant_repo_filter(job_id="job-7") == {
        "term": {"job_id": "job-7"}
    }


def test_tenant_and_job_filter_is_conjunctive() -> None:
    filter_body = build_tenant_repo_filter("tenant-a", job_id="job-7")
    must = filter_body["bool"]["must"]
    assert {"term": {"tenant_id": "tenant-a"}} in must
    assert {"term": {"job_id": "job-7"}} in must


def test_repo_and_job_filter_combines() -> None:
    filter_body = build_tenant_repo_filter(repo="repo:x", job_id="job-7")
    must = filter_body["bool"]["must"]
    assert {"term": {"repo": "repo:x"}} in must
    assert {"term": {"job_id": "job-7"}} in must


def test_default_tenant_and_job_keeps_legacy_unstamped_clause() -> None:
    filter_body = build_tenant_repo_filter(DEFAULT_TENANT_ID, job_id="job-7")
    must = filter_body["bool"]["must"]
    assert {"term": {"job_id": "job-7"}} in must
    tenant_clause = next(
        clause for clause in must if clause != {"term": {"job_id": "job-7"}}
    )
    assert tenant_clause["bool"]["minimum_should_match"] == 1
    assert {"term": {"tenant_id": DEFAULT_TENANT_ID}} in tenant_clause["bool"][
        "should"
    ]


# ── delete_projection ──────────────────────────────────────────────────────


def test_delete_by_job_id_removes_only_that_job(es) -> None:
    store, fake = es
    seed(store, "tenant-a", "job-1", count=2)
    seed(store, "tenant-a", "job-2", count=1)
    store.index_code_block(
        "repo:r", "s1", "N.java", "n", "void n() {}", tenant_id="tenant-a"
    )
    assert store.delete_projection(job_id="job-1") == 2
    remaining = {d["_source"].get("job_id") for d in fake.docs}
    assert remaining == {"job-2", None}


def test_delete_by_tenant_removes_only_that_tenant(es) -> None:
    store, fake = es
    seed(store, "tenant-a", "job-1", count=2)
    seed(store, "tenant-b", "job-2", count=1)
    assert store.delete_projection(tenant_id="tenant-a") == 2
    assert {d["_source"]["tenant_id"] for d in fake.docs} == {"tenant-b"}


def test_delete_default_tenant_includes_unstamped_legacy_docs(es) -> None:
    store, fake = es
    seed(store, DEFAULT_TENANT_ID, "job-1", count=1)
    fake.index(
        "x",
        {"repo": "r", "commit_sha": "s1", "path": "L.java", "symbol": "l"},
    )  # legacy doc without a tenant stamp
    seed(store, "tenant-b", "job-2", count=1)
    assert store.delete_projection(tenant_id=DEFAULT_TENANT_ID) == 2
    assert {d["_source"]["tenant_id"] for d in fake.docs} == {"tenant-b"}


def test_delete_tenant_and_job_are_conjunctive(es) -> None:
    store, fake = es
    seed(store, "tenant-a", "job-1", count=2)
    seed(store, "tenant-a", "job-2", count=1)
    seed(store, "tenant-b", "job-1", count=1)
    assert store.delete_projection(tenant_id="tenant-a", job_id="job-1") == 2
    remaining = [
        (d["_source"]["tenant_id"], d["_source"]["job_id"]) for d in fake.docs
    ]
    assert sorted(remaining) == [("tenant-a", "job-2"), ("tenant-b", "job-1")]


def test_delete_is_idempotent_second_call_returns_zero(es) -> None:
    store, fake = es
    seed(store, "tenant-a", "job-1", count=2)
    assert store.delete_projection(job_id="job-1") == 2
    assert store.delete_projection(job_id="job-1") == 0
    assert sum(len(batch) for batch in fake.delete_batches) == 2


def test_delete_missing_index_is_a_zero_noop_without_search() -> None:
    fake = FakeESProjection()  # index never created
    store = make_store(fake)
    assert store.delete_projection(job_id="job-1") == 0
    assert fake.search_bodies == []


def test_delete_missing_documents_is_a_zero_noop(es) -> None:
    store, _ = es
    assert store.delete_projection(job_id="no-such-job") == 0


def test_delete_requires_a_selector(es) -> None:
    store, _ = es
    with pytest.raises(ValueError, match="tenant_id or job_id"):
        store.delete_projection()


def test_delete_uses_per_document_delete_not_delete_by_query(es) -> None:
    store, fake = es
    seed(store, "tenant-a", "job-1", count=2)
    assert not hasattr(fake, "delete_by_query")
    assert store.delete_projection(job_id="job-1") == 2
    assert fake.search_bodies[0]["query"] == build_tenant_repo_filter(
        job_id="job-1"
    )
    assert fake.search_bodies[0]["size"] == _DELETE_PAGE_SIZE
    assert fake.search_bodies[0]["_source"] is False
    assert sum(len(batch) for batch in fake.delete_batches) == 2


def test_delete_paginates_batches(es) -> None:
    store, fake = es
    total = _DELETE_PAGE_SIZE + 5
    seed(store, "tenant-a", "job-1", count=total)
    assert store.delete_projection(job_id="job-1") == total
    assert [len(batch) for batch in fake.delete_batches] == [
        _DELETE_PAGE_SIZE,
        5,
    ]


# ── count_projection_docs ──────────────────────────────────────────────────


def test_count_by_job_and_tenant(es) -> None:
    store, _ = es
    seed(store, "tenant-a", "job-1", count=3)
    seed(store, "tenant-a", "job-2", count=1)
    assert store.count_projection_docs(job_id="job-1") == 3
    assert store.count_projection_docs(tenant_id="tenant-a") == 4
    assert store.count_projection_docs(tenant_id="tenant-a", job_id="job-2") == 1


def test_count_missing_index_is_zero() -> None:
    fake = FakeESProjection()
    store = make_store(fake)
    assert store.count_projection_docs(job_id="job-1") == 0


def test_count_requires_a_selector(es) -> None:
    store, _ = es
    with pytest.raises(ValueError, match="tenant_id or job_id"):
        store.count_projection_docs()


def test_count_default_tenant_includes_unstamped_legacy_docs(es) -> None:
    store, fake = es
    seed(store, DEFAULT_TENANT_ID, "job-1", count=1)
    fake.index(
        "x",
        {"repo": "r", "commit_sha": "s1", "path": "L.java", "symbol": "l"},
    )
    assert store.count_projection_docs(tenant_id=DEFAULT_TENANT_ID) == 2
