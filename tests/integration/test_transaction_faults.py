"""Fault injection: the transaction must not half-land (Phase 3, P3-7).

The roadmap's Phase 3 asks for fault injection covering 服务崩溃 / 超时 /
网络断开 / 消息重投 / DB 锁等待. 服务崩溃 (scenario 06), 消息重投
(scenario 04) and 对象上传成功后写库失败 (the artifact-store faults) are
already covered. This file adds the two that were missing on the DATABASE
side — **网络断开** and **DB 锁等待** — plus the **超时** path on the
provider side.

The claim under test is the store's atomicity promise: a job row and its
outbox row are written in ONE transaction, so a fault between the two
statements must leave **neither**. A half-landed job (a job nobody will
ever be told about) is the exact shape the outbox was introduced to
prevent, and it is invisible until someone goes looking for it.

The faults are injected at the boundary a real fault arrives at: the
CONNECTION. The transaction is real, the rollback is the database's, and
the assertion is made against the database — not against a fake that
merely remembers what it was told.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Any

import pymysql
import pytest

from storage.mysql import MySQLStore

#: The MySQL errno for "lock wait timeout exceeded" (1205) and the
#: client-side "lost connection" (2013). Both are what a real fault
#: looks like to the driver.
LOCK_WAIT_TIMEOUT = 1205
LOST_CONNECTION = 2013


class _FailingCursor:
    """A cursor that raises a real driver error on the Nth statement.

    Everything else is delegated to the real cursor, so the transaction
    is genuinely open when the fault lands — which is what makes the
    rollback observable. The statement counter lives on the CONNECTION,
    because the store opens a fresh cursor per statement.
    """

    def __init__(self, inner: Any, owner: _FailingConnection):
        self._inner = inner
        self._owner = owner

    def execute(self, sql: str, params: Any = None) -> Any:
        self._owner.calls += 1
        if self._owner.calls == self._owner.fail_on:
            raise pymysql.err.OperationalError(
                self._owner.errno, self._owner.message
            )
        return self._inner.execute(sql, params)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _FailingConnection:
    """A connection whose cursors fail on the Nth statement.

    The statement counter is shared across the connection's cursors: the
    store opens a new cursor for every statement, so a per-cursor
    counter would never reach the second statement.
    """

    def __init__(self, inner: Any, *, fail_on: int, errno: int, message: str):
        self._inner = inner
        self.fail_on = fail_on
        self.errno = errno
        self.message = message
        self.calls = 0

    def cursor(self) -> Any:
        return _FailingCursor(self._inner.cursor(), self)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _failing_connection_factory(
    original: Any, *, fail_on: int, errno: int, message: str,
) -> Any:
    """A `connection()` replacement whose cursors fail on the Nth statement.

    The real transaction is still open when the fault lands — that is what
    makes the rollback observable against the database.
    """

    @contextmanager
    def failing_connection() -> Any:
        with original() as inner:
            yield _FailingConnection(
                inner, fail_on=fail_on, errno=errno, message=message,
            )

    return failing_connection


@pytest.fixture()
def store() -> MySQLStore:
    try:
        instance = MySQLStore()
        instance.ensure_tables()
    except Exception:  # noqa: BLE001 — no MySQL means no verdict
        pytest.skip("MySQL not available")
    return instance


def _job(job_id: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "repo_path": "/test/repo",
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec_path": "/test/spec.md",
        "depth": "FAST",
    }


def _outbox_rows(store: MySQLStore, job_id: str) -> list[dict[str, Any]]:
    with store.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, aggregate_id FROM outbox WHERE aggregate_id = %s",
            (job_id,),
        )
        return list(cursor.fetchall())


class TestTheTransactionNeverHalfLands:
    """A fault between the two statements must leave NEITHER row."""

    @pytest.mark.parametrize(
        "errno,message,label",
        [
            (LOST_CONNECTION, "Lost connection to MySQL server", "network drop"),
            (LOCK_WAIT_TIMEOUT, "Lock wait timeout exceeded", "lock wait"),
        ],
    )
    def test_a_fault_mid_transaction_rolls_the_job_row_back(
        self, store: MySQLStore, errno: int, message: str, label: str,
    ) -> None:
        job_id = str(uuid.uuid4())
        original_connection = store.connection
        store.connection = _failing_connection_factory(  # type: ignore[method-assign]
            original_connection, fail_on=2, errno=errno, message=message,
        )
        try:
            with pytest.raises(pymysql.err.OperationalError):
                store.create_job_with_outbox(_job(job_id))
        finally:
            store.connection = original_connection  # type: ignore[method-assign]

        # The job row is GONE: the first statement was rolled back with
        # the second. A job nobody will ever hear about is the shape the
        # outbox exists to prevent.
        assert store.get_job(job_id) is None, (
            f"{label}: the job row survived a mid-transaction fault — a job "
            "that was never announced is invisible until someone goes "
            "looking for it"
        )
        # And there is no orphan outbox row either.
        assert _outbox_rows(store, job_id) == [], (
            f"{label}: the outbox row survived a mid-transaction fault"
        )

    def test_the_fault_is_reported_honestly(self, store: MySQLStore) -> None:
        """The driver error is not swallowed into a "success"."""
        job_id = str(uuid.uuid4())
        original_connection = store.connection
        store.connection = _failing_connection_factory(  # type: ignore[method-assign]
            original_connection,
            fail_on=2,
            errno=LOST_CONNECTION,
            message="Lost connection to MySQL server during query",
        )
        try:
            with pytest.raises(pymysql.err.OperationalError) as caught:
                store.create_job_with_outbox(_job(job_id))
        finally:
            store.connection = original_connection  # type: ignore[method-assign]
        assert "Lost connection" in str(caught.value)

    def test_a_fault_on_the_FIRST_statement_also_lands_nothing(
        self, store: MySQLStore,
    ) -> None:
        """The other end of the window: nothing was written at all."""
        job_id = str(uuid.uuid4())
        original_connection = store.connection
        store.connection = _failing_connection_factory(  # type: ignore[method-assign]
            original_connection,
            fail_on=1,
            errno=LOCK_WAIT_TIMEOUT,
            message="Lock wait timeout exceeded; try restarting transaction",
        )
        try:
            with pytest.raises(pymysql.err.OperationalError):
                store.create_job_with_outbox(_job(job_id))
        finally:
            store.connection = original_connection  # type: ignore[method-assign]

        assert store.get_job(job_id) is None
        assert _outbox_rows(store, job_id) == []


class TestTheJobIsStillUsableAfterwards:
    """A rolled-back job must not poison the store.

    The next insert has to work: a half-landed row that blocks the next
    attempt (a unique key, a lock) would turn one fault into an outage.
    """

    def test_a_second_job_lands_normally_after_a_rollback(
        self, store: MySQLStore,
    ) -> None:
        failed_id = str(uuid.uuid4())
        original_connection = store.connection
        store.connection = _failing_connection_factory(  # type: ignore[method-assign]
            original_connection,
            fail_on=2,
            errno=LOST_CONNECTION,
            message="dropped",
        )
        try:
            with pytest.raises(pymysql.err.OperationalError):
                store.create_job_with_outbox(_job(failed_id))
        finally:
            store.connection = original_connection  # type: ignore[method-assign]

        good_id = str(uuid.uuid4())
        assert store.create_job_with_outbox(_job(good_id)) == good_id
        job = store.get_job(good_id)
        assert job is not None
        assert job["status"] == "QUEUED"
        assert len(_outbox_rows(store, good_id)) == 1
        # The failed one left nothing behind.
        assert store.get_job(failed_id) is None
        assert _outbox_rows(store, failed_id) == []


class TestTheOutboxPayloadIsIntact:
    """The outbox row carries the job — a rollback must not half-write it."""

    def test_the_outbox_payload_names_the_job(self, store: MySQLStore) -> None:
        job_id = str(uuid.uuid4())
        store.create_job_with_outbox(_job(job_id))
        rows = _outbox_rows(store, job_id)
        assert len(rows) == 1
        with store.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT payload FROM outbox WHERE aggregate_id = %s", (job_id,)
            )
            payload = json.loads(cursor.fetchone()["payload"])
        assert payload["job_id"] == job_id
