"""P1.1 Integration tests: Job lifecycle with real MySQL."""

import contextlib
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from storage.mysql import InvalidStateTransition, MySQLStore


class TestJobLifecycle:
    """End-to-end job lifecycle tests with real MySQL."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.store = MySQLStore()
        try:
            self.store.ensure_tables()
        except Exception:
            pytest.skip("MySQL not available")

    def _create_job(self, status: str = "PENDING", **overrides) -> str:
        jid = str(uuid.uuid4())
        job = {
            "id": jid,
            "repo_path": "/test/repo",
            "base_ref": "base",
            "head_ref": "head",
            "spec_path": "/test/spec.md",
            "status": status,
            "depth": "FAST",
            **overrides,
        }
        self.store.insert_job(job)
        return jid

    def test_full_lifecycle_pending_to_blocked(self):
        jid = self._create_job("PENDING")
        assert self.store.transition_job_status(jid, "QUEUED")
        assert self.store.claim_job(jid, "worker-abc")
        assert self.store.transition_job_status(jid, "BLOCKED")

        job = self.store.get_job(jid)
        assert job["status"] == "BLOCKED"
        assert job["worker_id"] == "worker-abc"

    def test_full_lifecycle_pending_to_verified(self):
        jid = self._create_job("PENDING")
        self.store.transition_job_status(jid, "QUEUED")
        self.store.claim_job(jid, "worker-xyz")
        self.store.transition_job_status(jid, "VERIFIED")

        job = self.store.get_job(jid)
        assert job["status"] == "VERIFIED"

    def test_concurrent_claim_is_safe(self):
        """Multiple threads trying to claim the same QUEUED job: only one wins."""
        jid = self._create_job("QUEUED")
        results = []

        def try_claim(worker: str):
            store = MySQLStore()
            ok = store.claim_job(jid, worker)
            results.append((worker, ok))

        with ThreadPoolExecutor(max_workers=5) as pool:
            for i in range(5):
                pool.submit(try_claim, f"worker-{i}")

        winners = [r for r in results if r[1]]
        assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}: {results}"
        job = self.store.get_job(jid)
        assert job["status"] == "RUNNING"
        assert job["worker_id"] == winners[0][0]

    def test_new_head_sha_stales_inflight_jobs(self):
        jid1 = self._create_job("QUEUED")
        jid2 = self._create_job("RUNNING")
        jid3 = self._create_job("VERIFIED")  # terminal — not staled

        new_job_id = str(uuid.uuid4())
        staled = self.store.mark_stale_for_head("new-head-sha", new_job_id)

        assert jid1 in staled
        assert jid2 in staled
        assert jid3 not in staled

        assert self.store.get_job(jid1)["status"] == "STALE"
        assert self.store.get_job(jid2)["status"] == "STALE"
        assert self.store.get_job(jid3)["status"] == "VERIFIED"

        # Verify stale_replaced_by
        assert self.store.get_job(jid1)["stale_replaced_by"] == new_job_id

    def test_retry_loop_then_permanent_failure(self):
        jid = self._create_job("RUNNING")

        for attempt in range(3):
            self.store.transition_job_status(
                jid, "FAILED",
                error_msg=f"Attempt {attempt+1} failed",
                increment_retry=True,
            )
            if attempt < 2:
                self.store.transition_job_status(jid, "QUEUED")
                self.store.claim_job(jid, f"worker-{attempt+1}")

        # Final failure
        self.store.transition_job_status(jid, "ERROR", error_msg="Max retries exceeded")

        job = self.store.get_job(jid)
        assert job["status"] == "ERROR"
        assert job["retry_count"] == 3
        assert "Max retries exceeded" in job["last_error"]

    def test_transaction_rollback_on_error(self):
        """If a transition raises, the status should remain unchanged."""
        jid = self._create_job("PENDING")

        # Attempt illegal transition
        with contextlib.suppress(InvalidStateTransition):
            self.store.transition_job_status(jid, "BLOCKED")

        job = self.store.get_job(jid)
        assert job["status"] == "PENDING", "Status should be unchanged after failed transition"

    def test_get_jobs_by_status(self):
        self._create_job("QUEUED")
        self._create_job("QUEUED")
        self._create_job("RUNNING")

        queued = self.store.get_jobs_by_status("QUEUED")
        assert len(queued) == 2

        running = self.store.get_jobs_by_status("RUNNING")
        assert len(running) == 1

    def test_idempotent_transition(self):
        """Running the same CAS transition twice: second call is a no-op (returns False)."""
        jid = self._create_job("QUEUED")
        ok1 = self.store.claim_job(jid, "worker-1")
        ok2 = self.store.claim_job(jid, "worker-2")
        assert ok1
        assert not ok2, "Second CAS should fail because status is no longer QUEUED"

    def test_nonexistent_job_raises(self):
        with pytest.raises(InvalidStateTransition, match="not found"):
            self.store.transition_job_status("nonexistent-id", "RUNNING")
