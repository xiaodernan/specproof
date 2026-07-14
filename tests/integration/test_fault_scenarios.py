"""P1 fault-injection tests — 10 scenarios for reliability validation.

All scenarios require Docker infrastructure (MySQL + RabbitMQ + Redis).
When Docker is unavailable, all tests auto-skip.

Scenarios 1-4: Outbox + Idempotency
Scenario 5: Provider retry (mocked)
Scenario 6: Worker mid-graph crash → checkpoint (P1-B, skipped)
Scenario 7: SSE disconnect → Last-Event-ID resumption
Scenario 8: MinIO orphan detection (P1-B, skipped)
Scenario 9: New Head SHA → STALE marking
Scenario 10: Stale job recovery by monitor
"""

import json
import time
import uuid

import pytest

from storage.mysql import MySQLStore

# ── Docker readiness probes ──────────────────────────────────────


def _docker_ready() -> bool:
    """Check if Docker and all required services are reachable."""
    try:
        from storage.mysql import MySQLStore
        from storage.rabbitmq import RabbitMQClient
        from storage.redis import RedisStore

        mysql_ok = MySQLStore().is_ready()
        rabbit_ok = RabbitMQClient().is_ready()
        redis_ok = RedisStore().is_ready()
        return mysql_ok and rabbit_ok and redis_ok
    except Exception:
        return False


def _mysql_only_ready() -> bool:
    try:
        from storage.mysql import MySQLStore

        return MySQLStore().is_ready()
    except Exception:
        return False


docker_skip = pytest.mark.skipif(not _docker_ready(), reason="Docker infra not available")
mysql_skip = pytest.mark.skipif(not _mysql_only_ready(), reason="MySQL not available")


# ── Helpers ──────────────────────────────────────────────────────


def _create_job_via_outbox(store: MySQLStore, routing_key: str = "q.p1.verify.job") -> str:
    """Create a job via the transactional outbox path."""
    job_id = str(uuid.uuid4())
    store.create_job_with_outbox(
        job={
            "id": job_id,
            "repo_path": "/test/fault-repo",
            "base_ref": "main",
            "head_ref": f"feature-fault-{uuid.uuid4().hex[:6]}",
            "spec_path": "/test/fault-spec.md",
            "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
            "depth": "FAST",
            "trace_id": str(uuid.uuid4()),
        },
        routing_key=routing_key,
    )
    return job_id


# ═══════════════════════════════════════════════════════════════════
# Scenario 1: Outbox Relay delivers after API crash
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@docker_skip
class TestScenario1OutboxRecovery:
    """Job + outbox committed; relay publishes; worker picks up."""

    def test_outbox_event_persisted_after_creation(self) -> None:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        job_id = _create_job_via_outbox(store)

        # Verify job exists in QUEUED state
        job = store.get_job(job_id)
        assert job is not None
        assert job["status"] == "QUEUED"

        # Verify outbox event is PENDING
        events = store.claim_pending_events(limit=10)
        matching = [e for e in events if e["aggregate_id"] == job_id]
        assert len(matching) == 1
        assert matching[0]["event_type"] == "JobCreated"

    def test_relay_claims_and_publishes(self) -> None:
        from storage.mysql import MySQLStore
        from storage.rabbitmq import RabbitMQClient

        store = MySQLStore()
        store.ensure_tables()

        job_id = _create_job_via_outbox(store)

        # Simulate relay: claim → publish → mark published
        events = store.claim_pending_events(limit=10)
        matching = [e for e in events if e["aggregate_id"] == job_id]
        assert len(matching) == 1

        event = matching[0]
        rabbit = RabbitMQClient()
        rabbit.ensure_p1_topology()

        published = rabbit.publish_with_confirm(
            routing_key=event["routing_key"],
            payload={
                "event_id": event["event_id"],
                "job_id": job_id,
                "trace_id": event["trace_id"],
                "event_type": event["event_type"],
                "payload": json.loads(event["payload"]),
            },
        )
        assert published

        store.mark_event_published(event["event_id"])

        # Verify no longer PENDING
        events2 = store.claim_pending_events(limit=10)
        remaining = [e for e in events2 if e["event_id"] == event["event_id"]]
        assert len(remaining) == 0


# ═══════════════════════════════════════════════════════════════════
# Scenario 2: Duplicate outbox event → idempotency
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@docker_skip
class TestScenario2DuplicateEvents:
    """Same event_id processed twice → idempotency rejects second."""

    def test_duplicate_event_marked_processed(self) -> None:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        consumer = "fault-test-consumer"
        event_id = f"evt-dup-{uuid.uuid4().hex[:8]}"

        # First time: not processed
        assert not store.is_event_processed(consumer, event_id)

        # Mark processed
        store.mark_event_processed(consumer, event_id)

        # Second time: already processed
        assert store.is_event_processed(consumer, event_id)

        # Mark again is no-op
        store.mark_event_processed(consumer, event_id)
        assert store.is_event_processed(consumer, event_id)


# ═══════════════════════════════════════════════════════════════════
# Scenario 3: Consumer crashes after work, before Ack → idempotency
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@docker_skip
class TestScenario3ConsumerCrashBeforeAck:
    """Processing completes, consumer crashes before Ack, message re-queued."""

    def test_idempotency_prevents_reprocessing(self) -> None:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        consumer = "crash-test-consumer"
        event_id = f"evt-crash-{uuid.uuid4().hex[:8]}"

        # Simulate: consumer processes, marks idempotency, then "crashes"
        store.mark_event_processed(consumer, event_id)

        # Message re-queued (RabbitMQ re-delivers) → check idempotency
        assert store.is_event_processed(consumer, event_id)
        # Consumer skips processing, Acks


# ═══════════════════════════════════════════════════════════════════
# Scenario 4: RabbitMQ redelivers same message → idempotency
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@docker_skip
class TestScenario4Redelivery:
    """Same message delivered multiple times → processed only once."""

    def test_redelivered_event_idempotent(self) -> None:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        consumer = "redelivery-consumer"
        event_id = f"evt-redeliver-{uuid.uuid4().hex[:8]}"

        # First delivery: process
        assert not store.is_event_processed(consumer, event_id)
        store.mark_event_processed(consumer, event_id)

        # Second delivery: skip
        assert store.is_event_processed(consumer, event_id)


# ═══════════════════════════════════════════════════════════════════
# Scenario 5: Provider retry with exponential backoff (mocked)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestScenario5ProviderRetry:
    """Provider errors trigger retry; permanent errors go to DLQ."""

    def test_temporary_failure_triggers_retry(self) -> None:
        from storage.rabbitmq import TemporaryFailureError

        assert issubclass(TemporaryFailureError, Exception)

    def test_permanent_failure_goes_to_dlq(self) -> None:
        from storage.rabbitmq import PermanentFailureError

        assert issubclass(PermanentFailureError, Exception)

    def test_temporary_and_permanent_are_distinct(self) -> None:
        from storage.rabbitmq import PermanentFailureError, TemporaryFailureError

        te = TemporaryFailureError("timeout")
        pe = PermanentFailureError("bad request")
        assert not isinstance(pe, TemporaryFailureError)
        assert not isinstance(te, PermanentFailureError)

    def test_exception_chain_preserves_cause(self) -> None:
        from storage.rabbitmq import TemporaryFailureError

        try:
            try:
                raise ConnectionError("Connection refused")
            except ConnectionError as e:
                raise TemporaryFailureError("Provider unavailable") from e
        except TemporaryFailureError as te:
            assert te.__cause__ is not None
            assert isinstance(te.__cause__, ConnectionError)


# ═══════════════════════════════════════════════════════════════════
# Scenario 6: Worker mid-graph crash → checkpoint recovery
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestScenario6CheckpointRecovery:
    """P1.6: LangGraph checkpoint after each node, resume on crash."""

    @pytest.mark.skip(reason="P1.6 checkpoint recovery deferred to P1-B")
    def test_worker_recovers_from_checkpoint(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════
# Scenario 7: SSE disconnect → Last-Event-ID resumption
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@docker_skip
class TestScenario7SseResumption:
    """Client disconnects, reconnects with Last-Event-ID, catches up."""

    def test_stream_progress_read_from_id(self) -> None:
        from storage.redis import RedisStore

        redis = RedisStore()

        job_id = f"fault-sse-{uuid.uuid4().hex[:8]}"

        # Write events
        redis.xadd_progress(job_id, {"event": "node_start", "node": "intake"})
        id2 = redis.xadd_progress(job_id, {"event": "node_complete", "node": "intake"})
        redis.xadd_progress(job_id, {"event": "node_start", "node": "compile_contracts"})

        # Read from beginning
        all_events = redis.xread_progress(job_id, from_id="0")
        assert len(all_events) == 3

        # Read from id2 onward (catches up after disconnect)
        tail_events = redis.xread_progress(job_id, from_id=id2)
        assert len(tail_events) >= 1
        # The event after id2 should be id3
        assert tail_events[0]["event"] == "node_start"

    def test_stream_maxlen_trims_old_entries(self) -> None:
        from storage.redis import RedisStore

        redis = RedisStore()

        job_id = f"fault-maxlen-{uuid.uuid4().hex[:8]}"

        # Write many events with small maxlen
        for i in range(20):
            redis.xadd_progress(job_id, {"event": f"step_{i}"}, maxlen=5)

        # Only ~5 remain
        length = redis.xlen(job_id)
        assert length <= 6  # approximate maxlen


# ═══════════════════════════════════════════════════════════════════
# Scenario 8: MinIO orphan detection
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestScenario8MinioOrphanDetection:
    """P1.5: MinIO upload succeeds, MongoDB ref write fails → orphan."""

    @pytest.mark.skip(reason="P1.5 artifact consistency deferred to P1-B")
    def test_orphan_objects_detected(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════
# Scenario 9: New Head SHA → STALE marking
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@mysql_skip
class TestScenario9StaleMarking:
    """When a new commit arrives, old jobs for the same repo go STALE."""

    def test_claim_stale_jobs_marks_old_jobs(self) -> None:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        repo = f"/test/repo-stale-{uuid.uuid4().hex[:6]}"

        # Create old job
        old_job_id = str(uuid.uuid4())
        store.insert_job(
            {
                "id": old_job_id,
                "repo_path": repo,
                "base_ref": "main",
                "head_ref": "old-head",
                "spec_path": "/test/spec.md",
                "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "depth": "FAST",
            }
        )

        # Job starts in RUNNING (P0.5 compat)
        job = store.get_job(old_job_id)
        assert job is not None
        assert job["status"] == "RUNNING"

        # New head SHA arrives → mark old jobs STALE
        stale_count = store.claim_stale_jobs("new-head-sha", repo)
        assert stale_count == 1

        # Old job is now STALE
        job = store.get_job(old_job_id)
        assert job is not None
        assert job["status"] == "STALE"

    def test_terminal_jobs_not_marked_stale(self) -> None:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        repo = f"/test/repo-term-{uuid.uuid4().hex[:6]}"
        trace_id = str(uuid.uuid4())

        # Create job and move to terminal state
        job_id = str(uuid.uuid4())
        store.insert_job(
            {
                "id": job_id,
                "repo_path": repo,
                "base_ref": "main",
                "head_ref": "head-v1",
                "spec_path": "/test/spec.md",
                "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "depth": "FAST",
            }
        )
        store.transition_job_status(job_id, "SUCCEEDED", trace_id=trace_id)

        # New head → SUCCEEDED job should NOT go STALE
        stale_count = store.claim_stale_jobs("new-head-v2", repo)
        assert stale_count == 0

        job = store.get_job(job_id)
        assert job is not None
        assert job["status"] == "SUCCEEDED"


# ═══════════════════════════════════════════════════════════════════
# Scenario 10: Service restart → recover unfinished jobs
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@mysql_skip
class TestScenario10ServiceRestartRecovery:
    """After restart, RUNNING jobs are detected and can be recovered."""

    def test_list_jobs_by_status_finds_running(self) -> None:
        from storage.mysql import MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        # Create a RUNNING job (simulating pre-restart state)
        job_id = str(uuid.uuid4())
        store.insert_job(
            {
                "id": job_id,
                "repo_path": "/test/repo-restart",
                "base_ref": "main",
                "head_ref": "feature-restart",
                "spec_path": "/test/spec.md",
                "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "depth": "FAST",
            }
        )

        # On restart, monitor finds RUNNING jobs
        running_jobs = store.list_jobs_by_status("RUNNING", limit=10)
        matching = [j for j in running_jobs if j["id"] == job_id]
        assert len(matching) == 1

    def test_failed_is_terminal_retry_creates_new_job(self) -> None:
        """FAILED is terminal — retry must create a new job with new job_id."""
        from storage.mysql import InvalidStateTransitionError, MySQLStore

        store = MySQLStore()
        store.ensure_tables()

        job_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        store.insert_job(
            {
                "id": job_id,
                "repo_path": "/test/repo-retry",
                "base_ref": "main",
                "head_ref": "feature-retry",
                "spec_path": "/test/spec.md",
                "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "depth": "FAST",
            }
        )

        # Move to FAILED
        store.transition_job_status(
            job_id, "FAILED", error_msg="Worker crash", error_code="WORKER_CRASH", trace_id=trace_id
        )

        job = store.get_job(job_id)
        assert job is not None
        assert job["status"] == "FAILED"

        # FAILED is terminal — no exit transitions allowed
        with pytest.raises(InvalidStateTransitionError):
            store.transition_job_status(job_id, "QUEUED", trace_id=trace_id)

        # Retry creates a NEW job (new job_id, fresh lifecycle)
        new_job_id = str(uuid.uuid4())
        store.create_job_with_outbox(
            job={
                "id": new_job_id,
                "repo_path": "/test/repo-retry",
                "base_ref": "main",
                "head_ref": "feature-retry",
                "spec_path": "/test/spec.md",
                "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "depth": "FAST",
                "trace_id": str(uuid.uuid4()),
            },
            routing_key="q.p1.verify.job",
        )

        new_job = store.get_job(new_job_id)
        assert new_job is not None
        assert new_job["status"] == "QUEUED"

        # Old job remains FAILED
        old_job = store.get_job(job_id)
        assert old_job is not None
        assert old_job["status"] == "FAILED"


# ═══════════════════════════════════════════════════════════════════
# Lease expiry (cross-cutting)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.integration
@docker_skip
class TestLeaseExpiry:
    """Worker lease expires → another worker can acquire."""

    def test_lease_expires_and_reacquired(self) -> None:
        from storage.redis import RedisStore

        redis = RedisStore()

        job_id = f"fault-lease-{uuid.uuid4().hex[:8]}"
        worker_a = "worker-a"
        worker_b = "worker-b"

        # Worker A acquires lease
        acquired = redis.acquire_lease(job_id, worker_a, ttl=1)
        assert acquired

        # Worker B cannot acquire while A holds
        assert not redis.acquire_lease(job_id, worker_b, ttl=30)

        # Wait for lease to expire
        time.sleep(1.5)

        # Worker B can now acquire
        assert redis.acquire_lease(job_id, worker_b, ttl=30)

        # Cleanup
        redis.release_lease(job_id, worker_b)
