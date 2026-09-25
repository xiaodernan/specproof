"""P1.1 Unit tests: Job state machine validation."""

import contextlib
import json
import uuid
from typing import Any

import pytest

from storage.mysql import (
    _VALID_TRANSITIONS,
    TERMINAL_STATUSES,
    InvalidStateTransition,
    MySQLStore,
)


class _RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, list[Any]]] = []
        self.rowcount = 1

    def execute(self, sql: str, params: Any = None) -> None:
        self.statements.append((sql, list(params or [])))


class _RecordingConn:
    def __init__(self) -> None:
        self.cursor_obj = _RecordingCursor()

    def cursor(self) -> _RecordingCursor:
        return self.cursor_obj

    def __enter__(self) -> "_RecordingConn":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class TestTerminalWriteIsOneStatement:
    """The verdict and its evidence must become visible in ONE UPDATE (#63).

    Backend-independent on purpose: the DB-backed class below skips when no
    MySQL is reachable, and "status and summary share a statement" is exactly
    the kind of claim that has to be checkable on a laptop.
    """

    def _store(self) -> tuple[MySQLStore, _RecordingConn]:
        store = MySQLStore()
        conn = _RecordingConn()
        store.connection = lambda: conn  # type: ignore[method-assign]
        store.record_audit = lambda **kw: None  # type: ignore[method-assign]
        return store, conn

    def test_summary_rides_in_the_status_statement(self):
        store, conn = self._store()
        summary = {"verdict": "VERIFIED", "matrix_passed": 3}
        ok = store.transition_job_status(
            "job-1", "VERIFIED", from_status="RUNNING", summary=summary
        )
        assert ok
        statements = conn.cursor_obj.statements
        assert len(statements) == 1, (
            f"a terminal write is one statement, got {len(statements)}"
        )
        sql, params = statements[0]
        assert "status = %s" in sql
        assert "summary = %s" in sql
        assert "WHERE id = %s AND status = %s" in sql
        # Positional order is part of the contract: the WHERE pair is last.
        assert params[0] == "VERIFIED"
        assert params[-2] == "job-1"
        assert params[-1] == "RUNNING"
        assert json.loads(params[1]) == summary

    def test_no_summary_quietly_clears_an_existing_one(self):
        """Omitting `summary` must not emit the column at all.

        "Nothing new to say" and "clear the evidence" are different claims;
        a terminal transition that carries no summary has to leave whatever
        the row already holds untouched.
        """
        for kwargs in ({}, {"summary": None}):
            store, conn = self._store()
            assert store.transition_job_status(
                "job-2", "VERIFIED", from_status="RUNNING", **kwargs
            )
            sql, params = conn.cursor_obj.statements[0]
            assert "summary" not in sql, sql
            assert params == ["VERIFIED", "job-2", "RUNNING"]


class TestStateMachineStatic:
    """Validate the state machine definition itself (no DB needed)."""

    ALL_STATUSES = list(_VALID_TRANSITIONS.keys())

    def test_all_ten_statuses_defined(self):
        assert len(_VALID_TRANSITIONS) == 10
        all_statuses = [
            "PENDING", "QUEUED", "RUNNING", "WAITING_FOR_PROVIDER",
            "VERIFIED", "BLOCKED", "STALE", "FAILED", "CANCELLED",
            "ERROR",
        ]
        for s in all_statuses:
            assert s in _VALID_TRANSITIONS, f"Missing status: {s}"

    def test_terminal_statuses_have_no_exits(self):
        for s in TERMINAL_STATUSES:
            assert _VALID_TRANSITIONS[s] == set(), f"Terminal {s} should have no exits"

    def test_valid_transitions_are_recognized(self):
        """Legitimate transitions must all return True."""
        legitimate = [
            ("PENDING", "QUEUED"),
            ("PENDING", "ERROR"),
            ("QUEUED", "RUNNING"),
            ("QUEUED", "STALE"),
            ("QUEUED", "ERROR"),
            ("QUEUED", "CANCELLED"),
            ("RUNNING", "VERIFIED"),
            ("RUNNING", "BLOCKED"),
            ("RUNNING", "FAILED"),
            ("RUNNING", "STALE"),
            ("RUNNING", "ERROR"),
            ("RUNNING", "CANCELLED"),
            ("RUNNING", "WAITING_FOR_PROVIDER"),
            ("WAITING_FOR_PROVIDER", "QUEUED"),
            ("WAITING_FOR_PROVIDER", "FAILED"),
            ("FAILED", "QUEUED"),
            ("FAILED", "ERROR"),
            ("FAILED", "CANCELLED"),
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
        for s in ["PENDING", "QUEUED", "RUNNING", "WAITING_FOR_PROVIDER", "FAILED"]:
            assert not MySQLStore.is_terminal(s)


class TestStateMachineWithDB:
    """Tests that require a MySQL connection (integration-style but fast).

    Every row these tests write goes into the real `verification_jobs`
    table, so teardown deletes what the test created and then proves the
    row is gone (#73). A leftover RUNNING row is not harmless litter:
    `specproof ops recover` reads exactly that shape — RUNNING plus a stale
    updated_at — as a hung job and re-delivers it.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.store = MySQLStore()
        try:
            self.store.ensure_tables()
        except Exception:
            pytest.skip("MySQL not available")
        self.job_id = str(uuid.uuid4())
        self.created: list[str] = []
        try:
            yield
        finally:
            leftovers: list[str] = []
            for jid in self.created:
                with contextlib.suppress(Exception):
                    self.store.delete_job_records(jid)
                if self.store.get_job(jid) is not None:
                    leftovers.append(jid)
            assert not leftovers, (
                "test rows survived into the shared verification_jobs table: "
                f"{leftovers} — a leftover RUNNING row is what the reclaim "
                "pass steals (#73)"
            )

    def _track(self, jid: str) -> str:
        if jid not in self.created:
            self.created.append(jid)
        return jid

    def _insert_job(self, status: str = "PENDING") -> None:
        self._track(self.job_id)
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
        job2 = self._track(str(uuid.uuid4()))
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
            jid = self._track(str(uuid.uuid4()))
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
