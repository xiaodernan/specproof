"""P1.1 Unit tests: Job state machine validation."""

import uuid

import pytest

from storage.mysql import (
    TERMINAL_STATUSES,
    _VALID_TRANSITIONS,
    InvalidStateTransition,
    MySQLStore,
)


class TestStateMachineStatic:
    """Validate the state machine definition itself (no DB needed)."""

    ALL_STATUSES = list(_VALID_TRANSITIONS.keys())

    def test_all_eight_statuses_defined(self):
        assert len(_VALID_TRANSITIONS) == 8
        for s in ["PENDING", "QUEUED", "RUNNING", "VERIFIED", "BLOCKED", "STALE", "FAILED", "ERROR"]:
            assert s in _VALID_TRANSITIONS, f"Missing status: {s}"

    def test_terminal_statuses_have_no_exits(self):
        for s in TERMINAL_STATUSES:
            assert _VALID_TRANSITIONS[s] == set(), f"Terminal {s} should have no exits"

    def test_valid_transitions_are_recognized(self):
        """24 legitimate transitions must all return True."""
        legitimate = [
            ("PENDING", "QUEUED"),
            ("PENDING", "ERROR"),
            ("QUEUED", "RUNNING"),
            ("QUEUED", "STALE"),
            ("QUEUED", "ERROR"),
            ("RUNNING", "VERIFIED"),
            ("RUNNING", "BLOCKED"),
            ("RUNNING", "FAILED"),
            ("RUNNING", "STALE"),
            ("RUNNING", "ERROR"),
            ("FAILED", "QUEUED"),
            ("FAILED", "ERROR"),
        ]
        for from_s, to_s in legitimate:
            assert MySQLStore.is_valid_transition(from_s, to_s), (
                f"Should be valid: {from_s} -> {to_s}"
            )

    def test_invalid_transitions_are_rejected(self):
        """Key illegal transitions must all return False."""
        illegal = [
            # Skip steps
            ("PENDING", "RUNNING"),
            ("PENDING", "VERIFIED"),
            ("PENDING", "BLOCKED"),
            ("PENDING", "FAILED"),
            ("QUEUED", "VERIFIED"),
            ("QUEUED", "BLOCKED"),
            # Go backwards
            ("RUNNING", "PENDING"),
            ("RUNNING", "QUEUED"),
            ("VERIFIED", "PENDING"),
            ("VERIFIED", "RUNNING"),
            ("BLOCKED", "PENDING"),
            ("BLOCKED", "RUNNING"),
            ("STALE", "RUNNING"),
            ("STALE", "PENDING"),
            ("ERROR", "PENDING"),
            ("ERROR", "RUNNING"),
            # Terminal to anything
            ("VERIFIED", "FAILED"),
            ("BLOCKED", "FAILED"),
            ("STALE", "FAILED"),
            ("ERROR", "FAILED"),
            # FAILED to non-retry targets
            ("FAILED", "VERIFIED"),
            ("FAILED", "BLOCKED"),
            ("FAILED", "RUNNING"),
        ]
        for from_s, to_s in illegal:
            assert not MySQLStore.is_valid_transition(from_s, to_s), (
                f"Should be invalid: {from_s} -> {to_s}"
            )

    def test_is_terminal(self):
        for s in TERMINAL_STATUSES:
            assert MySQLStore.is_terminal(s)
        for s in ["PENDING", "QUEUED", "RUNNING", "FAILED"]:
            assert not MySQLStore.is_terminal(s)


class TestStateMachineWithDB:
    """Tests that require a MySQL connection (integration-style but fast)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.store = MySQLStore()
        try:
            self.store.ensure_tables()
        except Exception:
            pytest.skip("MySQL not available")
        self.job_id = str(uuid.uuid4())

    def _insert_job(self, status: str = "PENDING") -> None:
        self.store.insert_job({
            "id": self.job_id,
            "repo_path": "/test/repo",
            "base_ref": "base",
            "head_ref": "head",
            "spec_path": "/test/spec.md",
            "status": status,
            "depth": "FAST",
        })

    def test_transition_pending_to_queued(self):
        self._insert_job("PENDING")
        ok = self.store.transition_job_status(self.job_id, "QUEUED")
        assert ok
        job = self.store.get_job(self.job_id)
        assert job["status"] == "QUEUED"

    def test_transition_queued_to_running_with_worker(self):
        self._insert_job("QUEUED")
        ok = self.store.transition_job_status(
            self.job_id, "RUNNING", worker_id="worker-1"
        )
        assert ok
        job = self.store.get_job(self.job_id)
        assert job["status"] == "RUNNING"
        assert job["worker_id"] == "worker-1"

    def test_transition_running_to_blocked(self):
        self._insert_job("RUNNING")
        ok = self.store.transition_job_status(self.job_id, "BLOCKED")
        assert ok
        job = self.store.get_job(self.job_id)
        assert job["status"] == "BLOCKED"

    def test_transition_running_to_verified(self):
        self._insert_job("RUNNING")
        ok = self.store.transition_job_status(self.job_id, "VERIFIED")
        assert ok

    def test_failed_retry_to_queued(self):
        self._insert_job("FAILED")
        ok = self.store.transition_job_status(
            self.job_id, "QUEUED", increment_retry=True
        )
        assert ok
        job = self.store.get_job(self.job_id)
        assert job["status"] == "QUEUED"
        assert job["retry_count"] == 1

    def test_mark_stale_for_head(self):
        self._insert_job("QUEUED")
        job2 = str(uuid.uuid4())
        self.store.insert_job({
            "id": job2, "repo_path": "/test/repo",
            "base_ref": "base", "head_ref": "head2",
            "spec_path": "/test/spec.md", "status": "RUNNING", "depth": "FAST",
        })
        stale_ids = self.store.mark_stale_for_head("head3", "new-job-id")
        assert self.job_id in stale_ids
        assert job2 in stale_ids
        job = self.store.get_job(self.job_id)
        assert job["status"] == "STALE"
        assert job["stale_replaced_by"] == "new-job-id"

    def test_cas_prevents_concurrent_claim(self):
        """Two claim attempts on same QUEUED job: only one succeeds."""
        self._insert_job("QUEUED")
        ok1 = self.store.claim_job(self.job_id, "worker-A")
        ok2 = self.store.claim_job(self.job_id, "worker-B")
        assert ok1
        assert not ok2
        job = self.store.get_job(self.job_id)
        assert job["worker_id"] == "worker-A"

    def test_illegal_transition_raises(self):
        self._insert_job("PENDING")
        with pytest.raises(InvalidStateTransition, match="PENDING.*BLOCKED"):
            self.store.transition_job_status(self.job_id, "BLOCKED")

    def test_illegal_skip_raises(self):
        self._insert_job("PENDING")
        with pytest.raises(InvalidStateTransition, match="PENDING.*RUNNING"):
            self.store.transition_job_status(self.job_id, "RUNNING")

    def test_terminal_cannot_transition(self):
        for status in TERMINAL_STATUSES:
            jid = str(uuid.uuid4())
            self.store.insert_job({
                "id": jid, "repo_path": "/test/repo",
                "base_ref": "base", "head_ref": "head",
                "spec_path": "/test/spec.md", "status": status, "depth": "FAST",
            })
            with pytest.raises(InvalidStateTransition):
                self.store.transition_job_status(jid, "RUNNING")

    def test_transition_with_error_msg(self):
        self._insert_job("PENDING")
        self.store.transition_job_status(
            self.job_id, "ERROR", error_msg="Infrastructure failure: connection refused"
        )
        job = self.store.get_job(self.job_id)
        assert job["status"] == "ERROR"
        assert "connection refused" in job["last_error"]

    def test_full_happy_path(self):
        """PENDING → QUEUED → RUNNING → BLOCKED."""
        self._insert_job("PENDING")
        assert self.store.transition_job_status(self.job_id, "QUEUED")
        assert self.store.claim_job(self.job_id, "worker-1")
        assert self.store.transition_job_status(self.job_id, "BLOCKED")
        job = self.store.get_job(self.job_id)
        assert job["status"] == "BLOCKED"

    def test_full_error_path(self):
        """RUNNING → FAILED → QUEUED (retry) → RUNNING → ERROR (permanent)."""
        self._insert_job("RUNNING")
        assert self.store.transition_job_status(self.job_id, "FAILED", error_msg="LLM timeout")
        assert self.store.transition_job_status(self.job_id, "QUEUED", increment_retry=True)
        assert self.store.claim_job(self.job_id, "worker-2")
        assert self.store.transition_job_status(self.job_id, "ERROR", error_msg="Permanent failure")
        job = self.store.get_job(self.job_id)
        assert job["status"] == "ERROR"
        assert job["retry_count"] == 1
        assert "Permanent failure" in job["last_error"]
