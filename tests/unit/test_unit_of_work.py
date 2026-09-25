"""#83 — a failed rollback must not become the reported cause.

Measured origin: with a MySQL connection the server had already dropped,
`tests/integration/test_job_lifecycle.py` failed as
`pymysql.err.InterfaceError: (0, '')` raised from `storage/mysql.py`'s
`conn.rollback()`. The statement that actually broke was never reported —
every lost-connection red pointed at teardown instead. Five stores carried a
byte-identical `connection()`, so the same lie was available on all of them.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any

import pytest
from pymysql.err import InterfaceError

import storage
from storage.agent_jobs import MySqlAgentJobStore
from storage.billing import MySqlBillingStore
from storage.identity import MySqlIdentityStore
from storage.mysql import MySQLStore
from storage.object_metadata import MySQLObjectMetadataStore
from storage.unit_of_work import unit_of_work

STORE_CLASSES: list[type[Any]] = [
    MySQLStore,
    MySqlAgentJobStore,
    MySqlBillingStore,
    MySqlIdentityStore,
    MySQLObjectMetadataStore,
]


class PrimaryError(RuntimeError):
    """The real cause: whatever the body of the unit of work did."""


class TeardownError(RuntimeError):
    """A handle that was already gone talking back during teardown."""


class FakeConnection:
    def __init__(
        self,
        *,
        commit_error: Exception | None = None,
        rollback_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0
        self._commit_error = commit_error
        self._rollback_error = rollback_error
        self._close_error = close_error

    def commit(self) -> None:
        self.commits += 1
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self) -> None:
        self.rollbacks += 1
        if self._rollback_error is not None:
            raise self._rollback_error

    def close(self) -> None:
        self.closes += 1
        if self._close_error is not None:
            raise self._close_error


def _store(store_cls: type[Any], conn: FakeConnection) -> Any:
    # object.__new__ on purpose: this is a test about connection() teardown,
    # not about each store's config parsing.
    store = object.__new__(store_cls)
    store._connect = lambda: conn  # type: ignore[attr-defined]
    return store


def _teardown_logs(caplog: Any) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("storage.unit_of_work")
    ]


class TestCleanPath:
    def test_a_clean_body_commits_once_and_closes_once(self) -> None:
        conn = FakeConnection()
        with unit_of_work(lambda: conn) as live:
            assert live is conn
        assert (conn.commits, conn.rollbacks, conn.closes) == (1, 0, 1)

    def test_the_connection_reaches_the_body(self) -> None:
        conn = FakeConnection()
        seen = []
        with unit_of_work(lambda: conn) as live:
            seen.append(live)
        assert seen == [conn]


class TestTeardownNeverEatsTheCause:
    def test_a_body_failure_propagates_unchanged(self) -> None:
        conn = FakeConnection()
        with (
            pytest.raises(PrimaryError, match="the statement that broke"),
            unit_of_work(lambda: conn),
        ):
            raise PrimaryError("the statement that broke")
        assert (conn.commits, conn.rollbacks, conn.closes) == (0, 1, 1)

    def test_a_rollback_that_raises_does_not_replace_the_cause(self) -> None:
        conn = FakeConnection(rollback_error=InterfaceError(0, ""))
        with pytest.raises(PrimaryError, match="lost connection"), unit_of_work(lambda: conn):
            raise PrimaryError("lost connection during a query")
        assert conn.rollbacks == 1

    def test_a_close_that_raises_does_not_replace_the_cause(self) -> None:
        # This is the case that used to be worst: an exception raised in
        # `finally` discards the in-flight one entirely.
        conn = FakeConnection(close_error=TeardownError("close on a dead socket"))
        with pytest.raises(PrimaryError, match="the real cause"), unit_of_work(lambda: conn):
            raise PrimaryError("the real cause")

    def test_both_teardown_steps_may_fail_and_the_cause_still_wins(self) -> None:
        conn = FakeConnection(
            rollback_error=InterfaceError(0, ""),
            close_error=TeardownError("gone"),
        )
        with pytest.raises(PrimaryError), unit_of_work(lambda: conn):
            raise PrimaryError("query failed")
        assert (conn.rollbacks, conn.closes) == (1, 1)

    def test_a_failed_commit_is_reported_rather_than_a_rollback(self) -> None:
        conn = FakeConnection(commit_error=InterfaceError(0, ""))
        with pytest.raises(InterfaceError), unit_of_work(lambda: conn):
            pass
        assert conn.rollbacks == 1


class TestTeardownFailuresStayVisible:
    def test_a_suppressed_rollback_error_is_logged_as_teardown_only(self, caplog) -> None:
        conn = FakeConnection(rollback_error=InterfaceError(0, ""))
        with (
            caplog.at_level(logging.WARNING, logger="storage.unit_of_work"),
            pytest.raises(PrimaryError),
            unit_of_work(lambda: conn),
        ):
            raise PrimaryError("query failed")
        assert any("rollback" in message for message in _teardown_logs(caplog))

    def test_a_suppressed_close_error_is_logged(self, caplog) -> None:
        conn = FakeConnection(close_error=TeardownError("dead socket"))
        with (
            caplog.at_level(logging.WARNING, logger="storage.unit_of_work"),
            pytest.raises(PrimaryError),
            unit_of_work(lambda: conn),
        ):
            raise PrimaryError("query failed")
        assert any("close" in message for message in _teardown_logs(caplog))

    def test_the_clean_path_logs_nothing(self, caplog) -> None:
        conn = FakeConnection()
        with caplog.at_level(logging.WARNING, logger="storage.unit_of_work"), unit_of_work(
            lambda: conn
        ):
            pass
        assert _teardown_logs(caplog) == []


class TestConnectivityFailures:
    def test_a_connection_that_never_opened_gets_no_teardown(self) -> None:
        def connect() -> FakeConnection:
            raise PrimaryError("host is unreachable")

        with pytest.raises(PrimaryError, match="unreachable"), unit_of_work(connect):
            pass


class TestEveryStoreSharesOneImplementation:
    @pytest.mark.parametrize("store_cls", STORE_CLASSES, ids=lambda c: c.__name__)
    def test_store_connection_reports_the_cause_not_the_rollback(self, store_cls) -> None:
        conn = FakeConnection(rollback_error=InterfaceError(0, ""))
        store = _store(store_cls, conn)
        with pytest.raises(PrimaryError, match="query died"), store.connection():
            raise PrimaryError("query died")
        assert (conn.rollbacks, conn.closes) == (1, 1)

    @pytest.mark.parametrize("store_cls", STORE_CLASSES, ids=lambda c: c.__name__)
    def test_store_connection_still_commits_and_closes(self, store_cls) -> None:
        conn = FakeConnection()
        store = _store(store_cls, conn)
        with store.connection() as live:
            assert live is conn
        assert (conn.commits, conn.rollbacks, conn.closes) == (1, 0, 1)

    @pytest.mark.parametrize("store_cls", STORE_CLASSES, ids=lambda c: c.__name__)
    def test_the_rollback_lives_in_one_place_now(self, store_cls) -> None:
        source = inspect.getsource(store_cls.connection)
        assert "unit_of_work" in source, store_cls.__name__
        assert "conn.rollback()" not in source, store_cls.__name__

    def test_no_module_in_storage_reintroduces_a_local_rollback(self) -> None:
        storage_pkg = Path(storage.__file__).parent
        offenders = [
            path.name
            for path in sorted(storage_pkg.glob("*.py"))
            if "conn.rollback()" in path.read_text(encoding="utf-8")
        ]
        assert offenders == []
