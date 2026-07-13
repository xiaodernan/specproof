"""Integration tests for P1.1 MySQL state machine + P1.2 outbox.

Requires a running MySQL instance. Set env vars or skip automatically:
  MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""

import uuid

import pytest

from storage.mysql import (
    InvalidStateTransitionError,
    JobNotFoundError,
    MySQLStore,
    OptimisticLockFailureError,
)


def _mysql_ready() -> bool:
    try:
        store = MySQLStore()
        return store.is_ready()
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _mysql_ready(), reason="MySQL not available"),
]


@pytest.fixture
def store() -> MySQLStore:
    s = MySQLStore()
    s.ensure_tables()
    return s


@pytest.fixture
def job_id() -> str:
    return str(uuid.uuid4())


class TestJobLifecycle:
    """Full lifecycle via P0.5 insert_job + manual transitions."""

    def test_full_happy_path(self, store: MySQLStore, job_id: str) -> None:
        # P0.5-compatible API: starts in RUNNING
        store.insert_job({
            "id": job_id,
            "repo_path": "/test/repo",
            "base_ref": "main",
            "head_ref": "feature-x",
            "spec_path": "/test/spec.md",
            "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
            "depth": "FAST",
        })

        job = store.get_job(job_id)
        assert job is not None
        assert job["status"] == "RUNNING"

        # Complete through valid transitions
        trace_id = str(uuid.uuid4())
        worker = "integration-test-worker"

        store.transition_job_status(job_id, "WAITING_FOR_PROVIDER",
                                     worker_id=worker, trace_id=trace_id)
        store.transition_job_status(job_id, "RUNNING",
                                     worker_id=worker, trace_id=trace_id)
        store.transition_job_status(job_id, "SUCCEEDED",
                                     worker_id=worker, trace_id=trace_id)

        final = store.get_job(job_id)
        assert final is not None
        assert final["status"] == "SUCCEEDED"


class TestCasOptimisticLocking:
    """CAS version-check prevents lost updates."""

    def test_concurrent_update_version_conflict(
        self, store: MySQLStore, job_id: str,
    ) -> None:
        store.insert_job({
            "id": job_id,
            "repo_path": "/test/repo2",
            "base_ref": "main",
            "head_ref": "feature-y",
            "spec_path": "/test/spec2.md",
            "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
            "depth": "FAST",
        })

        trace_id = str(uuid.uuid4())
        # RUNNING → QUEUED is not valid; run a valid transition first
        store.transition_job_status(job_id, "WAITING_FOR_PROVIDER", trace_id=trace_id)

        job = store.get_job(job_id)
        assert job is not None
        v1 = job["version"]

        # First transition succeeds
        store.transition_job_status(job_id, "RUNNING", trace_id=trace_id)

        # Second transition with stale expected_version must fail
        with pytest.raises(OptimisticLockFailureError):
            store.transition_job_status(
                job_id, "FAILED",
                expected_version=v1,  # stale
                trace_id=trace_id,
            )


class TestInvalidTransitions:
    """Illegal transitions must be rejected at DB integration level."""

    def test_skip_queued_rejected(self, store: MySQLStore, job_id: str) -> None:
        store.insert_job({
            "id": job_id,
            "repo_path": "/test/repo3",
            "base_ref": "main",
            "head_ref": "feature-z",
            "spec_path": "/test/spec3.md",
            "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
            "depth": "FAST",
        })
        # RUNNING → CREATED is backward/invalid
        with pytest.raises(InvalidStateTransitionError):
            store.transition_job_status(job_id, "CREATED")

    def test_terminal_no_exit(self, store: MySQLStore, job_id: str) -> None:
        store.insert_job({
            "id": job_id,
            "repo_path": "/test/repo4",
            "base_ref": "main",
            "head_ref": "feature-w",
            "spec_path": "/test/spec4.md",
            "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
            "depth": "FAST",
        })
        trace_id = str(uuid.uuid4())
        store.transition_job_status(job_id, "SUCCEEDED", trace_id=trace_id)

        # SUCCEEDED is terminal
        with pytest.raises(InvalidStateTransitionError):
            store.transition_job_status(job_id, "RUNNING")

    def test_job_not_found(self, store: MySQLStore) -> None:
        with pytest.raises(JobNotFoundError):
            store.transition_job_status("nonexistent-id-12345", "RUNNING")


class TestOutboxTxIntegrity:
    """P1.2: Job + outbox in same transaction."""

    def test_create_job_with_outbox(self, store: MySQLStore) -> None:
        job_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        result_id = store.create_job_with_outbox(
            job={
                "id": job_id,
                "repo_path": "/test/repo-ob",
                "base_ref": "main",
                "head_ref": "feature-ob",
                "spec_path": "/test/spec-ob.md",
                "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "depth": "FAST",
                "trace_id": trace_id,
            },
            routing_key="q.p1.verify.job",
        )
        assert result_id == job_id

        # Job exists and is QUEUED (auto-transitioned from CREATED)
        job = store.get_job(job_id)
        assert job is not None
        assert job["status"] == "QUEUED"

        # Outbox event exists
        events = store.claim_pending_events(limit=10)
        matching = [e for e in events if e["aggregate_id"] == job_id]
        assert len(matching) >= 1, f"No outbox event found for job {job_id}"

    def test_outbox_batch_claim_idempotent(self, store: MySQLStore) -> None:
        """Two claim_pending_events calls don't overlap (SKIP LOCKED)."""
        job_ids = []
        for i in range(3):
            jid = str(uuid.uuid4())
            job_ids.append(jid)
            store.create_job_with_outbox(
                job={
                    "id": jid,
                    "repo_path": f"/test/repo-ob-{i}",
                    "base_ref": "main",
                    "head_ref": f"feature-ob-{i}",
                    "spec_path": "/test/spec-ob.md",
                    "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
                    "depth": "FAST",
                    "trace_id": str(uuid.uuid4()),
                },
                routing_key="q.p1.verify.job",
            )

        batch1 = store.claim_pending_events(limit=10)
        batch2 = store.claim_pending_events(limit=10)

        ids1 = {e["event_id"] for e in batch1}
        ids2 = {e["event_id"] for e in batch2}
        assert len(ids1 & ids2) == 0, "Overlapping claims between batches"


class TestIdempotency:
    """P1.3: processed_events deduplication."""

    def test_event_processing_dedup(self, store: MySQLStore) -> None:
        consumer = "test-consumer"
        event_id = f"evt-{uuid.uuid4().hex[:12]}"

        assert not store.is_event_processed(consumer, event_id)
        store.mark_event_processed(consumer, event_id)
        assert store.is_event_processed(consumer, event_id)

        # Marking again is idempotent (INSERT IGNORE)
        store.mark_event_processed(consumer, event_id)
        assert store.is_event_processed(consumer, event_id)

    def test_different_consumers_independent(self, store: MySQLStore) -> None:
        event_id = f"evt-{uuid.uuid4().hex[:12]}"

        store.mark_event_processed("worker-1", event_id)
        assert store.is_event_processed("worker-1", event_id)
        assert not store.is_event_processed("worker-2", event_id)


class TestAuditTrail:
    """State transitions produce audit log entries."""

    def test_transition_creates_audit_log(self, store: MySQLStore, job_id: str) -> None:
        store.insert_job({
            "id": job_id,
            "repo_path": "/test/repo-audit",
            "base_ref": "main",
            "head_ref": "feature-audit",
            "spec_path": "/test/spec-audit.md",
            "config_hash": f"hash-{uuid.uuid4().hex[:8]}",
            "depth": "FAST",
        })
        trace_id = str(uuid.uuid4())

        store.transition_job_status(job_id, "WAITING_FOR_PROVIDER", trace_id=trace_id)
        store.transition_job_status(
            job_id, "RUNNING",
            worker_id="audit-worker", trace_id=trace_id,
        )

        logs = store.get_job_audit_log(job_id)
        assert len(logs) >= 2, f"Expected >=2 audit entries, got {len(logs)}"
        # event_type is always "status_transition"; details has {from, to}
        transitions = []
        for entry in logs:
            details = entry.get("details") or {}
            transitions.append((details.get("from"), details.get("to")))
        assert ("RUNNING", "WAITING_FOR_PROVIDER") in transitions
        assert ("WAITING_FOR_PROVIDER", "RUNNING") in transitions
