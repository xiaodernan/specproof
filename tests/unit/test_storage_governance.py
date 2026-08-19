"""§14.2 storage governance unit tests (fakes only — no Docker, no DB).

Covers the three governance surfaces completed for P6:

- Outbox relay: DLQ state (per-row retry deferral + dead-letter past
  max_retries), publish-after-confirm ordering, and the six relay
  metrics (pending, oldest event age, failure rate, retry count,
  dead-letter count, last success ts) via observability.metrics.
- MinIO: governed object_path naming (tenant/repo/job/type/version),
  rejection of user-controlled raw paths before any client call, and
  digest/size/media-type/version returns on upload + download checks.
- Elasticsearch: delete-by-tenant/repo filter helper and tenant/source
  stamping on every indexed document.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from contracts.events import DEFAULT_TENANT_ID
from observability.metrics import snapshot
from storage.elasticsearch import ElasticsearchStore, build_tenant_repo_filter
from storage.minio import (
    DigestMismatchError,
    InvalidObjectPathError,
    MinIOClient,
    object_path,
    validate_object_path,
)
from storage.outbox_relay import (
    COUNTER_DEAD_LETTERED,
    COUNTER_PUBLISHED,
    METRIC_DEAD_LETTERS,
    METRIC_FAILURE_RATE,
    METRIC_LAST_SUCCESS_TS,
    METRIC_OLDEST_AGE_SECONDS,
    METRIC_PENDING,
    METRIC_RETRY_COUNT,
    OutboxRelay,
)

FIXED_NOW = 1_800_000_000.0


def _outbox_row(
    row_id: int = 1, retry_count: int = 0, event_type: str = "JobCreated",
) -> dict[str, Any]:
    return {
        "id": row_id,
        "aggregate_id": "job-1",
        "event_type": event_type,
        "routing_key": "q.p1.verify.job",
        "payload": json.dumps({"job_id": "job-1", "repo_path": "/repo"}),
        "retry_count": retry_count,
    }


# ═══════════════════════════════════════════════════════════════
# Outbox relay — DLQ state, publish-after-confirm, metrics
# ═══════════════════════════════════════════════════════════════

class FakeRelayMySQL:
    """Records every relay call in order; rows/stats are injected."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        stats: dict[str, Any] | None = None,
        events: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.rows = rows or []
        self.stats: dict[str, Any] = stats or {
            "pending": 0,
            "dead_letters": 0,
            "retries": 0,
            "oldest_created_at": None,
            "last_success": None,
        }
        self.events = events if events is not None else []

    def fetch_pending_outbox_rows(self, limit: int) -> list[dict[str, Any]]:
        self.events.append(("fetch", limit))
        return self.rows

    def mark_outbox_published(self, outbox_id: int) -> None:
        self.events.append(("published", outbox_id))

    def mark_outbox_failed(
        self, outbox_id: int, error: str, retry_after_seconds: float
    ) -> None:
        self.events.append(("failed", outbox_id, error, retry_after_seconds))

    def dead_letter_outbox_row(self, outbox_id: int, error: str) -> None:
        self.events.append(("dead", outbox_id, error))

    def outbox_stats(self) -> dict[str, Any]:
        self.events.append(("stats",))
        return dict(self.stats)


class FakeRabbit:
    """Publishes to a shared event list, or raises on demand."""

    def __init__(
        self,
        events: list[tuple[Any, ...]] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self.events = events if events is not None else []
        self.fail_with = fail_with

    def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        self.events.append(("publish", routing_key, payload["event_id"]))
        if self.fail_with is not None:
            raise self.fail_with


def _relay(
    rows: list[dict[str, Any]],
    *,
    stats: dict[str, Any] | None = None,
    max_retries: int = 5,
    fail_with: Exception | None = None,
) -> tuple[OutboxRelay, FakeRelayMySQL, FakeRabbit, list[tuple[Any, ...]]]:
    events: list[tuple[Any, ...]] = []
    mysql = FakeRelayMySQL(rows=rows, stats=stats, events=events)
    rabbit = FakeRabbit(events=events, fail_with=fail_with)
    relay = OutboxRelay(
        mysql=mysql,  # type: ignore[arg-type]  # fake duck-types MySQLStore
        rabbitmq=rabbit,  # type: ignore[arg-type]  # fake duck-types RabbitMQClient
        max_retries=max_retries,
        now_fn=lambda: FIXED_NOW,
    )
    return relay, mysql, rabbit, events


def test_marks_published_only_after_broker_confirm() -> None:
    relay, _mysql, _rabbit, events = _relay([_outbox_row(7)])
    assert relay.drain_pending() == 1
    publish_at = events.index(("publish", "q.p1.verify.job", "outbox-7"))
    published_at = events.index(("published", 7))
    assert publish_at < published_at
    assert ("failed", 7) not in events and ("dead", 7) not in events


def test_failed_publish_defers_retry_and_stops_the_batch() -> None:
    relay, _mysql, _rabbit, events = _relay(
        [_outbox_row(1), _outbox_row(2)], fail_with=ConnectionError("down")
    )
    assert relay.drain_pending() == 0
    # Exactly one attempt: the batch stops after the first failure.
    assert sum(1 for event in events if event[0] == "publish") == 1
    assert ("failed", 1, "down", 1.0) in events
    assert ("published", 1) not in events and ("published", 2) not in events
    assert relay.failure_rate() == 1.0
    assert relay._backoff == 1


def test_dead_letters_after_max_retries_instead_of_retrying_forever() -> None:
    relay, _mysql, _rabbit, events = _relay(
        [_outbox_row(9, retry_count=5)], max_retries=5,
        fail_with=ConnectionError("still down"),
    )
    assert relay.drain_pending() == 0
    assert ("dead", 9, "still down") in events
    assert ("failed", 9, "still down", 1.0) not in events


def test_failure_records_dead_letter_counter() -> None:
    before = snapshot()["counters"].get(COUNTER_DEAD_LETTERED, 0.0)
    relay, _mysql, _rabbit, _events = _relay(
        [_outbox_row(4, retry_count=5)], max_retries=5,
        fail_with=ConnectionError("down"),
    )
    relay.drain_pending()
    assert snapshot()["counters"].get(COUNTER_DEAD_LETTERED, 0.0) == before + 1


def test_successful_drain_increments_publish_counter_and_sets_ts_gauge() -> None:
    before = snapshot()["counters"].get(COUNTER_PUBLISHED, 0.0)
    relay, _mysql, _rabbit, _events = _relay([_outbox_row(3)])
    assert relay.drain_pending() == 1
    gauges = snapshot()["gauges"]
    assert snapshot()["counters"].get(COUNTER_PUBLISHED, 0.0) == before + 1
    assert gauges[METRIC_LAST_SUCCESS_TS] == FIXED_NOW


def test_refresh_metrics_publishes_the_six_governance_gauges() -> None:
    oldest = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    last_success = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)
    stats = {
        "pending": 7,
        "dead_letters": 2,
        "retries": 3,
        "oldest_created_at": oldest,
        "last_success": last_success,
    }
    relay, _mysql, _rabbit, events = _relay([], stats=stats)
    relay.refresh_metrics()
    gauges = snapshot()["gauges"]
    assert gauges[METRIC_PENDING] == 7.0
    assert gauges[METRIC_DEAD_LETTERS] == 2.0
    assert gauges[METRIC_RETRY_COUNT] == 3.0
    assert gauges[METRIC_OLDEST_AGE_SECONDS] == FIXED_NOW - oldest.timestamp()
    assert gauges[METRIC_LAST_SUCCESS_TS] == last_success.timestamp()
    assert gauges[METRIC_FAILURE_RATE] == 0.0
    assert ("stats",) in events


def test_oldest_age_falls_back_to_zero_without_rows() -> None:
    relay, _mysql, _rabbit, _events = _relay([])
    relay.refresh_metrics()
    gauges = snapshot()["gauges"]
    assert gauges[METRIC_OLDEST_AGE_SECONDS] == 0.0
    assert gauges[METRIC_PENDING] == 0.0


def test_last_success_gauge_falls_back_to_in_process_ts() -> None:
    relay, _mysql, _rabbit, _events = _relay([_outbox_row(5)])
    relay.drain_pending()  # sets the in-process last-success timestamp
    relay.refresh_metrics()  # stats have last_success = None
    assert snapshot()["gauges"][METRIC_LAST_SUCCESS_TS] == FIXED_NOW


def test_failure_rate_gauge_reflects_attempts_in_process() -> None:
    relay, _mysql, _rabbit, _events = _relay(
        [_outbox_row(1), _outbox_row(2)], fail_with=ConnectionError("down")
    )
    relay.drain_pending()
    relay.refresh_metrics()
    assert snapshot()["gauges"][METRIC_FAILURE_RATE] == 1.0


# ═══════════════════════════════════════════════════════════════
# MinIO — governed naming, path rejection, digest metadata
# ═══════════════════════════════════════════════════════════════

class FakeMinio:
    """In-memory MinIO stand-in recording every client call."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.calls: list[tuple[str, str]] = []

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: Any,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.calls.append(("put", object_name))
        self.objects[object_name] = data.read()
        self.metadata[object_name] = dict(metadata or {})

    def stat_object(self, bucket_name: str, object_name: str) -> Any:
        self.calls.append(("stat", object_name))
        if object_name not in self.objects:
            raise FileNotFoundError(object_name)
        return SimpleNamespace(
            size=len(self.objects[object_name]),
            content_type="application/octet-stream",
            metadata=dict(self.metadata.get(object_name, {})),
        )

    def get_object(self, bucket_name: str, object_name: str) -> Any:
        self.calls.append(("get", object_name))
        if object_name not in self.objects:
            raise FileNotFoundError(object_name)
        data = self.objects[object_name]
        return SimpleNamespace(
            read=lambda: data,
            close=lambda: None,
        )


@pytest.fixture()
def minio_client() -> tuple[MinIOClient, FakeMinio]:
    fake = FakeMinio()
    client = MinIOClient()
    client._client = fake  # type: ignore[assignment]  # test double
    return client, fake


def test_object_path_builds_governed_name() -> None:
    assert (
        object_path("tenant-a", "repo-x", "job-9", "report", "v2")
        == "tenant-a/repo-x/job-9/report/v2"
    )


def test_object_path_rejects_traversal_and_unsafe_segments() -> None:
    for segment in ("..", "a/b", "a\b", "a b", "", "."):
        with pytest.raises(InvalidObjectPathError):
            object_path(segment, "repo", "job", "type", "v1")


def test_validate_object_path_rejects_user_controlled_raw_paths() -> None:
    for name in (
        "../x", "/etc/passwd", "a\b", "", "a/../b", "a//b", "a b",
        "x" * 1025, "ü", "-lead", "_lead",
    ):
        with pytest.raises(InvalidObjectPathError):
            validate_object_path(name)


def test_validate_object_path_accepts_governed_names() -> None:
    name = "tenant-a/repo-x/job-9/report/v2"
    assert validate_object_path(name) == name
    assert validate_object_path(name, tenant="tenant-a") == name


def test_validate_object_path_enforces_tenant_prefix() -> None:
    name = "tenant-b/repo-x/job-9/report/v2"
    with pytest.raises(InvalidObjectPathError):
        validate_object_path(name, tenant="tenant-a")


def test_put_governed_object_returns_digest_size_media_type_version(
    minio_client: tuple[MinIOClient, FakeMinio],
) -> None:
    client, fake = minio_client
    result = client.put_governed_object(
        "specproof-bug-capsules",
        tenant="tenant-a",
        repo="repo-x",
        job="job-9",
        artifact_type="capsule",
        version="v2",
        data=b"capsule-bytes",
        content_type="application/zip",
    )
    assert result["object_name"] == "tenant-a/repo-x/job-9/capsule/v2"
    assert result["tenant"] == "tenant-a"
    assert result["version"] == "v2"
    assert result["sha256"] == hashlib.sha256(b"capsule-bytes").hexdigest()
    assert result["size_bytes"] == len(b"capsule-bytes")
    assert result["content_type"] == "application/zip"
    assert fake.calls == [("put", "tenant-a/repo-x/job-9/capsule/v2")]
    assert fake.metadata["tenant-a/repo-x/job-9/capsule/v2"][
        "X-Amz-Meta-Sha256"
    ] == result["sha256"]


def test_upload_rejects_raw_path_before_any_client_call(
    minio_client: tuple[MinIOClient, FakeMinio],
) -> None:
    client, fake = minio_client
    with pytest.raises(InvalidObjectPathError):
        client.upload_bytes("bucket", "../../etc/passwd", b"x")
    assert fake.calls == []


def test_put_object_with_digest_stores_sha256_metadata(
    minio_client: tuple[MinIOClient, FakeMinio],
) -> None:
    client, fake = minio_client
    result = client.put_object_with_digest(
        "bucket", "tenant-a/repo-x/job-9/report/v2", b"payload"
    )
    assert fake.metadata["tenant-a/repo-x/job-9/report/v2"][
        "X-Amz-Meta-Sha256"
    ] == hashlib.sha256(b"payload").hexdigest()
    assert result["size_bytes"] == len(b"payload")


def test_download_enforces_tenant_prefix_before_get(
    minio_client: tuple[MinIOClient, FakeMinio],
) -> None:
    client, fake = minio_client
    with pytest.raises(InvalidObjectPathError):
        client.download_bytes(
            "bucket", "other-tenant/x", tenant="tenant-a"
        )
    assert fake.calls == []


def test_download_verifies_expected_sha256(
    minio_client: tuple[MinIOClient, FakeMinio],
) -> None:
    client, fake = minio_client
    client.upload_bytes("bucket", "tenant-a/r/j/t/v1", b"bytes")
    good = hashlib.sha256(b"bytes").hexdigest()
    assert (
        client.download_bytes(
            "bucket", "tenant-a/r/j/t/v1", expected_sha256=good
        )
        == b"bytes"
    )
    with pytest.raises(DigestMismatchError):
        client.download_bytes(
            "bucket", "tenant-a/r/j/t/v1", expected_sha256="0" * 64
        )


# ═══════════════════════════════════════════════════════════════
# Elasticsearch — tenant/repo filter + tenant/source stamping
# ═══════════════════════════════════════════════════════════════

class FakeESGovernance:
    """Records delete_by_query bodies and indexed documents."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self.delete_queries: list[dict[str, Any]] = []

    @property
    def indices(self) -> FakeESGovernance:
        return self

    def exists(self, index: str) -> bool:  # noqa: ARG002
        return True

    def create(self, index: str, body: dict[str, Any]) -> None:  # noqa: ARG002
        return None

    def delete(self, index: str, ignore_unavailable: bool = False) -> None:  # noqa: ARG002
        self.docs = []

    def bulk(
        self, operations: list[Any], refresh: bool = False
    ) -> dict[str, Any]:
        for i in range(0, len(operations), 2):
            self.docs.append(operations[i + 1])
        return {"errors": False}

    def index(
        self, index: str, document: dict[str, Any], refresh: bool = False
    ) -> dict[str, Any]:
        self.docs.append(document)
        return {"result": "created"}

    def delete_by_query(
        self,
        index: str,
        body: dict[str, Any],
        refresh: bool = False,
        wait_for_completion: bool = True,
    ) -> dict[str, Any]:
        self.delete_queries.append({
            "index": index,
            "body": body,
            "refresh": refresh,
            "wait_for_completion": wait_for_completion,
        })
        return {"deleted": 5}


@pytest.fixture()
def es_store() -> tuple[ElasticsearchStore, FakeESGovernance]:
    fake = FakeESGovernance()
    store = ElasticsearchStore()
    store._client = fake  # type: ignore[assignment]  # test double
    return store, fake


def test_filter_helper_matches_tenant_and_repo() -> None:
    filter_body = build_tenant_repo_filter("tenant-a", "repo-x")
    must = filter_body["bool"]["must"]
    assert {"term": {"repo": "repo-x"}} in must
    assert {"term": {"tenant_id": "tenant-a"}} in must


def test_filter_helper_default_tenant_includes_unstamped_legacy_docs() -> None:
    filter_body = build_tenant_repo_filter(DEFAULT_TENANT_ID)
    should = filter_body["bool"]["should"]
    assert {"term": {"tenant_id": DEFAULT_TENANT_ID}} in should
    assert {
        "bool": {"must_not": [{"exists": {"field": "tenant_id"}}]}
    } in should
    assert filter_body["bool"]["minimum_should_match"] == 1


def test_filter_helper_non_default_tenant_is_a_plain_term() -> None:
    assert build_tenant_repo_filter("tenant-b") == {
        "term": {"tenant_id": "tenant-b"}
    }
    assert build_tenant_repo_filter(repo="repo-x") == {
        "term": {"repo": "repo-x"}
    }
    assert build_tenant_repo_filter() == {"match_all": {}}


def test_delete_by_tenant_repo_uses_the_governed_filter(
    es_store: tuple[ElasticsearchStore, FakeESGovernance],
) -> None:
    store, fake = es_store
    assert store.delete_by_tenant_repo("tenant-a", "repo-x") == 5
    assert len(fake.delete_queries) == 1
    call = fake.delete_queries[0]
    assert call["index"] == store.INDEX_CODE
    assert call["refresh"] is True
    assert call["wait_for_completion"] is True
    assert call["body"]["query"] == build_tenant_repo_filter(
        "tenant-a", "repo-x"
    )


def test_delete_tenant_uses_tenant_only_filter(
    es_store: tuple[ElasticsearchStore, FakeESGovernance],
) -> None:
    store, fake = es_store
    assert store.delete_tenant("tenant-b") == 5
    assert fake.delete_queries[0]["body"]["query"] == build_tenant_repo_filter(
        "tenant-b"
    )


def test_index_repository_stamps_tenant_and_source(
    es_store: tuple[ElasticsearchStore, FakeESGovernance],
) -> None:
    store, fake = es_store
    files = {"a.java": "class A { public void m() {} }"}
    count = store.index_repository(
        "repo:test", "abc123", files,
        tenant_id="tenant-a", source_type="code",
    )
    assert count >= 1
    assert fake.docs
    assert all(doc["tenant_id"] == "tenant-a" for doc in fake.docs)
    assert all(doc["source_type"] == "code" for doc in fake.docs)
    assert all(doc["repo"] == "repo:test" for doc in fake.docs)


def test_index_code_block_stamps_tenant_and_source(
    es_store: tuple[ElasticsearchStore, FakeESGovernance],
) -> None:
    store, fake = es_store
    store.index_code_block(
        "repo:test", "abc123", "A.java", "m",
        "void m() {}", tenant_id="tenant-c", source_type="evidence",
    )
    assert fake.docs == [{
        "repo": "repo:test",
        "tenant_id": "tenant-c",
        "source_type": "evidence",
        "commit_sha": "abc123",
        "path": "A.java",
        "symbol": "m",
        "language": "java",
        "content": "void m() {}",
        "start_line": 0,
        "end_line": 0,
    }]


def test_default_stamping_is_default_tenant_and_code(
    es_store: tuple[ElasticsearchStore, FakeESGovernance],
) -> None:
    store, fake = es_store
    store.index_code_block("repo:test", "abc123", "A.java", "m", "void m() {}")
    assert fake.docs[0]["tenant_id"] == DEFAULT_TENANT_ID
    assert fake.docs[0]["source_type"] == "code"
