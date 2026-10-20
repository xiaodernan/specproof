"""Execution-budget expiry: the EXPIRED terminal state's producer (P3).

The reclaim pass answers "the worker died" (the lease TTL expired). This
answers the OTHER stuck shape: the worker is alive but the job will never
finish — a sandbox that never returns, a test that hangs. Without a
deadline such a job sits in an in-flight status until a human notices by
hand.

The tests pin the four properties that matter:

* a job past its budget becomes EXPIRED, and the reason names the budget;
* a job INSIDE its budget is untouched — the deadline is not a sweep that
  expires everything;
* a job that already reached a terminal state is untouched;
* every expiry is audited, and the expiry is counted.

Real MySQL: the deadline is measured with the DATABASE clock
(TIMESTAMPDIFF against NOW()), so a skewed test host cannot make a job
look expired (or un-expired).
"""

from __future__ import annotations

import uuid

import pytest

from storage.mysql import MySQLStore


@pytest.fixture()
def store() -> MySQLStore:
    try:
        instance = MySQLStore()
        instance.ensure_tables()
    except Exception:  # noqa: BLE001 — no MySQL means no verdict
        pytest.skip("MySQL not available")
    return instance


def _insert(
    store: MySQLStore,
    *,
    status: str,
    age_seconds: int,
    budget: int,
) -> str:
    """Insert one job whose created_at is *age_seconds* in the past."""
    job_id = str(uuid.uuid4())
    with store.connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO verification_jobs "
            "(id, repo_path, base_ref, head_ref, spec_path, status, depth, "
            " max_execution_seconds, created_at, updated_at) "
            "VALUES (%s, '/test/repo', 'base', 'head', '/test/spec.md', %s, 'FAST', "
            " %s, NOW(3) - INTERVAL %s SECOND, NOW(3) - INTERVAL %s SECOND)",
            (job_id, status, budget, age_seconds, age_seconds),
        )
    return job_id


def _status(store: MySQLStore, job_id: str) -> str:
    job = store.get_job(job_id)
    assert job is not None
    return str(job.get("status") or "")


class TestExpireOverdueJobs:
    def test_a_job_past_its_budget_is_expired(
        self, store: MySQLStore,
    ) -> None:
        job_id = _insert(
            store, status="RUNNING", age_seconds=7200, budget=3600,
        )
        expired = store.expire_overdue_jobs()
        assert job_id in expired
        assert _status(store, job_id) == "EXPIRED"

    def test_the_reason_names_the_budget(
        self, store: MySQLStore,
    ) -> None:
        job_id = _insert(
            store, status="RUNNING", age_seconds=7200, budget=3600,
        )
        store.expire_overdue_jobs()
        job = store.get_job(job_id)
        assert job is not None
        detail = str(job.get("last_error") or "")
        assert "execution_budget_exhausted" in detail
        assert "3600" in detail

    def test_a_job_inside_its_budget_is_untouched(
        self, store: MySQLStore,
    ) -> None:
        job_id = _insert(
            store, status="RUNNING", age_seconds=60, budget=3600,
        )
        store.expire_overdue_jobs()
        assert _status(store, job_id) == "RUNNING"

    def test_a_terminal_job_is_untouched(
        self, store: MySQLStore,
    ) -> None:
        job_id = _insert(
            store, status="VERIFIED", age_seconds=7200, budget=3600,
        )
        store.expire_overdue_jobs()
        assert _status(store, job_id) == "VERIFIED"

    def test_every_in_flight_state_is_subject_to_the_deadline(
        self, store: MySQLStore,
    ) -> None:
        """A job that crashed in PREPARING is just as stuck as one in RUNNING."""
        for status in ("QUEUED", "PREPARING", "CONTRACT_REVIEW", "RUNNING", "REVIEWING"):
            job_id = _insert(
                store, status=status, age_seconds=7200, budget=3600,
            )
            store.expire_overdue_jobs()
            assert _status(store, job_id) == "EXPIRED", status

    def test_the_expiry_is_audited(
        self, store: MySQLStore,
    ) -> None:
        job_id = _insert(
            store, status="RUNNING", age_seconds=7200, budget=3600,
        )
        store.expire_overdue_jobs()
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT action, to_status FROM audit_logs WHERE job_id = %s",
                (job_id,),
            )
            rows = cur.fetchall()
        assert rows, "an expiry must leave an audit trail"
        actions = {str(r["action"]) for r in rows}
        assert "job_expired_execution_budget" in actions

    def test_expiring_twice_changes_nothing(
        self, store: MySQLStore,
    ) -> None:
        job_id = _insert(
            store, status="RUNNING", age_seconds=7200, budget=3600,
        )
        first = store.expire_overdue_jobs()
        second = store.expire_overdue_jobs()
        assert job_id in first
        assert job_id not in second, "an expired job is terminal, not re-expired"

    def test_the_deadline_column_has_a_usable_default(
        self, store: MySQLStore,
    ) -> None:
        """A row written without the column must still carry a budget.

        'No deadline' and 'the deadline is far away' must not look alike —
        a NULL budget would make the expiry check skip the row forever.
        """
        job_id = str(uuid.uuid4())
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO verification_jobs "
                "(id, repo_path, base_ref, head_ref, spec_path, status, depth, "
                " created_at, updated_at) "
                "VALUES (%s, '/test/repo', 'base', 'head', '/test/spec.md', "
                "'QUEUED', 'FAST', NOW(3), NOW(3))",
                (job_id,),
            )
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT max_execution_seconds FROM verification_jobs WHERE id = %s",
                (job_id,),
            )
            row = cur.fetchone()
        assert row is not None
        value = row["max_execution_seconds"] if isinstance(row, dict) else row[0]
        assert int(value) > 0
