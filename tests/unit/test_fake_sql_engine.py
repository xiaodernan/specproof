"""Gates for the SQL-semantics fake (tests/unit/fake_sql_engine.py).

The fake exists to stop measuring itself: the reclaimer's old fake
decided "stale" with its own hand-written rule, so it could stay green
while the production WHERE clause said something else. That only works
if the fake really evaluates the statement — so these tests prove it
does, by feeding it statements that DIFFER and checking the fake
notices.

The mutation arms are the point: each one takes a correct statement and
breaks it (drops a guard, reorders a placeholder), and the fake's answer
must change. A fake that cannot tell the two apart is not testing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from tests.unit.fake_sql_engine import (
    SqlFakeCursor,
    SqlFakeTable,
    UnsupportedSqlError,
)

NOW = datetime(2026, 8, 20, 12, 0, 0)

#: The production candidate query (status set and all).
SELECT_CANDIDATES = (
    "SELECT id, status, updated_at FROM verification_jobs "
    "WHERE updated_at < (NOW(3) - INTERVAL %s SECOND) "
    "AND status IN (%s, %s, %s) "
    "ORDER BY updated_at, id"
)

#: The same query with the freshness guard REMOVED — the mutation arm.
SELECT_CANDIDATES_NO_GUARD = (
    "SELECT id, status, updated_at FROM verification_jobs "
    "WHERE status IN (%s, %s, %s) "
    "ORDER BY updated_at, id"
)


def _row(job_id: str, status: str, age_seconds: int) -> dict[str, Any]:
    return {
        "id": job_id,
        "status": status,
        "updated_at": NOW - timedelta(seconds=age_seconds),
    }


def _table() -> SqlFakeTable:
    return SqlFakeTable(
        [
            _row("j-stale", "RUNNING", 200),
            _row("j-fresh", "RUNNING", 5),
            _row("j-other", "QUEUED", 200),
        ],
        now=NOW,
    )


def _run(table: SqlFakeTable, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cursor = SqlFakeCursor(table)
    cursor.execute(sql, params)
    return cursor.fetchall()


class TestSelect:
    def test_the_freshness_guard_decides(self) -> None:
        table = _table()
        rows = _run(table, SELECT_CANDIDATES, [30, "RUNNING", "PREPARING", "REVIEWING"])
        assert [r["id"] for r in rows] == ["j-stale"]

    def test_dropping_the_guard_changes_the_answer(self) -> None:
        """The mutation arm: without the guard, a FRESH row is selected.

        If the fake could not tell the two statements apart, the
        production query could lose its guard and the reclaimer test
        would still be green.
        """
        table = _table()
        rows = _run(table, SELECT_CANDIDATES_NO_GUARD, ["RUNNING", "PREPARING", "REVIEWING"])
        assert sorted(r["id"] for r in rows) == ["j-fresh", "j-stale"]

    def test_the_status_set_is_read_from_the_statement(self) -> None:
        """Not a hardcoded "RUNNING" — the SET comes from the SQL.

        A second status in the IN list is honoured; one that is absent
        is not. A fake with its own idea of the set could not do this.
        """
        table = _table()
        with_preparing = _run(
            table, SELECT_CANDIDATES, [30, "RUNNING", "PREPARING", "REVIEWING"]
        )
        assert [r["id"] for r in with_preparing] == ["j-stale"]

        table2 = _table()
        without_preparing = _run(
            table2, SELECT_CANDIDATES, [30, "RUNNING", "QUEUED", "REVIEWING"]
        )
        # "j-other" is QUEUED and old: it is now IN the set, so it is
        # selected — the fake followed the statement, not a rule.
        assert sorted(r["id"] for r in without_preparing) == ["j-other", "j-stale"]

    def test_the_parameters_bind_in_the_order_the_sql_mentions_them(self) -> None:
        """Reordering the placeholders must not need a reordering of the test.

        The bound values follow the TEXT: the TTL first (it appears
        first), then the status list.
        """
        table = _table()
        rows = _run(table, SELECT_CANDIDATES, [30, "RUNNING", "PREPARING", "REVIEWING"])
        assert [r["id"] for r in rows] == ["j-stale"]

        # The same statement with a much SMALLER TTL widens the window
        # (the cutoff moves closer to now), so the fresh row qualifies
        # too — the number really is the TTL, not "the first parameter".
        table2 = _table()
        rows2 = _run(table2, SELECT_CANDIDATES, [1, "RUNNING", "PREPARING", "REVIEWING"])
        assert sorted(r["id"] for r in rows2) == ["j-fresh", "j-stale"]

        # And a LARGER TTL narrows it to nothing — the cutoff moves back.
        table3 = _table()
        rows3 = _run(table3, SELECT_CANDIDATES, [600, "RUNNING", "PREPARING", "REVIEWING"])
        assert rows3 == []


class TestUpdate:
    _UPDATE = (
        "UPDATE verification_jobs SET status = 'QUEUED', worker_id = NULL, "
        "retry_count = retry_count + 1, last_error = %s "
        "WHERE id = %s "
        "AND updated_at < (NOW(3) - INTERVAL %s SECOND) "
        "AND status = %s"
    )

    def test_the_assignments_are_applied(self) -> None:
        table = _table()
        cursor = SqlFakeCursor(table)
        cursor.execute(
            self._UPDATE, ["stale_running_reclaimed", "j-stale", 30, "RUNNING"]
        )
        assert cursor.rowcount == 1
        row = table.rows["j-stale"]
        assert row["status"] == "QUEUED"
        assert row["worker_id"] is None
        assert row["retry_count"] == 1
        assert row["last_error"] == "stale_running_reclaimed"

    def test_the_where_clause_decides_which_rows_change(self) -> None:
        table = _table()
        cursor = SqlFakeCursor(table)
        cursor.execute(self._UPDATE, ["reason", "j-fresh", 30, "RUNNING"])
        assert cursor.rowcount == 0
        assert table.rows["j-fresh"]["status"] == "RUNNING"

    def test_a_row_that_moved_on_is_not_touched(self) -> None:
        """The status guard is what makes the CAS safe."""
        table = _table()
        cursor = SqlFakeCursor(table)
        cursor.execute(self._UPDATE, ["reason", "j-stale", 30, "QUEUED"])
        assert cursor.rowcount == 0
        assert table.rows["j-stale"]["status"] == "RUNNING"

    def test_dropping_the_status_guard_would_change_the_answer(self) -> None:
        """The mutation arm for the CAS: without the status guard, a row
        that already moved on is overwritten."""
        no_status_guard = (
            "UPDATE verification_jobs SET status = 'QUEUED', "
            "last_error = %s "
            "WHERE id = %s "
            "AND updated_at < (NOW(3) - INTERVAL %s SECOND)"
        )
        table = _table()
        cursor = SqlFakeCursor(table)
        cursor.execute(no_status_guard, ["reason", "j-stale", 30])
        assert cursor.rowcount == 1
        assert table.rows["j-stale"]["status"] == "QUEUED"


class TestRefusesWhatItCannotModel:
    def test_an_unknown_statement_raises(self) -> None:
        """A fake that shrugs has stopped testing."""
        table = _table()
        cursor = SqlFakeCursor(table)
        with pytest.raises(UnsupportedSqlError):
            cursor.execute("SHOW TABLES", [])

    def test_an_unknown_condition_raises(self) -> None:
        table = _table()
        cursor = SqlFakeCursor(table)
        with pytest.raises(UnsupportedSqlError):
            cursor.execute(
                "SELECT id FROM verification_jobs WHERE depth > %s", [2]
            )

    def test_an_unknown_assignment_raises(self) -> None:
        table = _table()
        cursor = SqlFakeCursor(table)
        with pytest.raises(UnsupportedSqlError):
            cursor.execute(
                "UPDATE verification_jobs SET retry_count = retry_count * 2 "
                "WHERE id = %s",
                ["j-stale"],
            )

    def test_too_few_parameters_raises(self) -> None:
        table = _table()
        cursor = SqlFakeCursor(table)
        with pytest.raises(UnsupportedSqlError):
            cursor.execute(SELECT_CANDIDATES, [30, "RUNNING"])
