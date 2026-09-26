"""Go/No-Go #13 read path: the feedback table must actually be readable.

Two defects lived here at once, both measured on the real MySQL 8.4 on
2026-09-26 (a probe script, now this file):

1. ``list_feedback`` and ``feedback_stats`` indexed their rows
   positionally (``row[0]``) while this store connects with
   ``cursorclass=DictCursor`` — so BOTH readers of the acceptance-rate
   table raised ``KeyError: 0`` on every real call. The unit tests never
   saw it because their fake store returned dicts from methods, not from
   a cursor.
2. One reviewer could POST the same verdict twice and each POST added a
   row (fresh uuid), inflating the numerator of ``acceptance_rate``.
   Migration 0012 bounds it at one row per (finding, reviewer) and
   ``insert_feedback`` upserts.

The cursor fakes below are deliberately dict-row shaped: they are the
shape pymysql produces, which is the only way this file can prove point 1
without a database.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from storage.mysql import MySQLConfig, MySQLStore

FEEDBACK_COLUMNS = (
    "id", "job_id", "tenant_id", "finding_id", "contract_id",
    "severity", "verdict", "reason", "created_by", "created_at",
)


@dataclass
class _Reply:
    """One canned cursor response, in call order."""

    rowcount: int = 1
    one: dict[str, Any] | None = None
    many: list[dict[str, Any]] = field(default_factory=list)


class FakeCursor:
    def __init__(self, replies: list[_Reply]) -> None:
        self._pending = list(replies)
        self.calls: list[tuple[str, Any]] = []
        self.rowcount = 0
        self._current = _Reply()

    def execute(self, sql: str, args: Any = None) -> None:
        self.calls.append((sql, args))
        self._current = self._pending.pop(0) if self._pending else _Reply()
        self.rowcount = self._current.rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._current.one

    def fetchall(self) -> list[dict[str, Any]]:
        return self._current.many


class FakeConn:
    def __init__(self, replies: list[_Reply]) -> None:
        self.cursor_obj = FakeCursor(replies)

    def cursor(self) -> FakeCursor:
        return self.cursor_obj


@contextlib.contextmanager
def _fake_connection(replies: list[_Reply]):
    """Swap MySQLStore.connection() for one scripted dict-row cursor."""
    conn = FakeConn(replies)

    @contextlib.contextmanager
    def connection():  # noqa: ANN202 — mirrors the store's own signature
        yield conn

    store = MySQLStore.__new__(MySQLStore)
    store.connection = connection  # type: ignore[method-assign]
    yield store, conn


def _dict_row(**overrides: Any) -> dict[str, Any]:
    row = dict.fromkeys(FEEDBACK_COLUMNS)
    row.update(
        {
            "id": "row-1", "job_id": "j-1", "tenant_id": None,
            "finding_id": "f-1", "contract_id": "AUTH-01",
            "severity": "BLOCKER", "verdict": "accept", "reason": None,
            "created_by": "u1", "created_at": None,
        }
    )
    row.update(overrides)
    return row


# ── 1. the read path must read DictCursor rows by column name ──


def test_list_feedback_maps_dict_rows_by_column_name() -> None:
    with _fake_connection([_Reply(many=[_dict_row(), _dict_row(id="row-2")])]) as (store, _):
        rows = store.list_feedback("j-1")
    assert [r["id"] for r in rows] == ["row-1", "row-2"]
    assert rows[0]["created_by"] == "u1"
    assert rows[0]["verdict"] == "accept"
    assert set(rows[0]) == set(FEEDBACK_COLUMNS)


def test_list_feedback_keeps_created_at_none_as_none() -> None:
    class _Ts:
        def isoformat(self) -> str:
            return "2026-09-26T03:00:00"

    with _fake_connection([_Reply(many=[_dict_row(created_at=_Ts())])]) as (store, _):
        rows = store.list_feedback("j-1")
    assert rows[0]["created_at"] == "2026-09-26T03:00:00"


def test_feedback_stats_uses_an_aliased_count() -> None:
    """COUNT(*) has no column NAME, and DictCursor keys by name.

    Without `AS n` the row is {"COUNT(*)": 3} and the lookup silently
    becomes a KeyError — an alias is part of the read contract.
    """
    replies = [
        _Reply(many=[
            {"verdict": "accept", "n": 2},
            {"verdict": "reject", "n": 1},
        ])
    ]
    with _fake_connection(replies) as (store, conn):
        stats = store.feedback_stats("j-1")
    assert "AS n" in conn.cursor_obj.calls[0][0]
    assert stats["accepted"] == 2 and stats["rejected"] == 1
    assert stats["acceptance_rate_pct"] == 66.7


def test_feedback_stats_without_verdict_rows_reports_none_not_zero() -> None:
    with _fake_connection([_Reply(many=[])]) as (store, _):
        stats = store.feedback_stats("j-1")
    assert stats["acceptance_rate_pct"] is None
    assert stats["no_feedback_not_counted"] is True


# ── 2. insert_feedback upserts and reports which of the three happened ──


def _payload(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": str(uuid.uuid4()), "job_id": "j-1", "tenant_id": None,
        "finding_id": "f-1", "contract_id": "AUTH-01",
        "severity": "BLOCKER", "verdict": "accept", "reason": None,
        "created_by": "u1",
    }
    row.update(overrides)
    return row


def test_insert_feedback_created_echoes_the_generated_id() -> None:
    payload = _payload()
    with _fake_connection([_Reply(rowcount=1)]) as (store, conn):
        result = store.insert_feedback(payload)
    assert result == {"state": "created", "id": payload["id"]}
    # Nothing to look up: the insert just made this the only row.
    assert len(conn.cursor_obj.calls) == 1


@pytest.mark.parametrize("rowcount", [0, 2], ids=["unchanged", "replaced"])
def test_insert_feedback_restated_reads_back_the_stored_id(rowcount: int) -> None:
    payload = _payload(id=str(uuid.uuid4()))
    # Two statements on one connection: the upsert, then the id read-back.
    replies = [_Reply(rowcount=rowcount), _Reply(one={"id": "row-first"})]
    with _fake_connection(replies) as (store, conn):
        result = store.insert_feedback(payload)
    assert result["state"] == ("unchanged" if rowcount == 0 else "replaced")
    assert result["id"] == "row-first", (
        "the caller's fresh uuid was never stored; echoing it would "
        "point the UI at a row that does not exist"
    )
    assert conn.cursor_obj.calls[1][0].startswith("SELECT id FROM finding_feedback")
    assert conn.cursor_obj.calls[1][1] == (payload["finding_id"], payload["created_by"])


def test_insert_feedback_upserts_on_the_unique_key() -> None:
    """The statement must be an upsert on (finding_id, created_by)."""
    with _fake_connection([_Reply(rowcount=1)]) as (store, conn):
        store.insert_feedback(_payload())
    sql = conn.cursor_obj.calls[0][0]
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "INSERT INTO finding_feedback" in sql


# ── 3. the same contract against the real MySQL 8.4 ──


@pytest.fixture()
def live_store() -> MySQLStore:
    store = MySQLStore()
    try:
        store.ensure_tables()
        with store.connection() as conn:
            conn.cursor().execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 — no MySQL here is a coverage fact
        pytest.skip(f"MySQL is not reachable: {exc}")
    return store


def test_real_mysql_one_verdict_per_reviewer(live_store: MySQLStore) -> None:
    """Three POSTs from one reviewer collapse into one verdict row.

    Proves 0012's unique key, the upsert, the read path and the rate all
    at once, on the storage backend the release gate actually uses.
    """
    config = MySQLConfig.from_env()
    assert config.database == "specproof_test", (
        f"#75 isolation contract redirected feedback writes to {config.database}"
    )
    job_id, finding_id = str(uuid.uuid4()), str(uuid.uuid4())
    reviewer_a, reviewer_b = "probe-84-a", "probe-84-b"
    try:
        with live_store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO verification_jobs (id, repo_path, base_ref, "
                "head_ref, spec_path, status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (job_id, "/test/84", "a", "b", "spec.md", "VERIFIED"),
            )
            cur.execute(
                "INSERT INTO findings (id, job_id, contract_id, severity, "
                "confidence, evidence_type) VALUES (%s, %s, %s, %s, %s, %s)",
                (finding_id, job_id, "C-84", "BLOCKER", 0.9, "test"),
            )

        def verdict(reviewer: str, verdict_: str, **kw: Any) -> dict[str, Any]:
            return _payload(
                id=str(uuid.uuid4()), job_id=job_id, finding_id=finding_id,
                created_by=reviewer, verdict=verdict_, **kw,
            )

        first = live_store.insert_feedback(verdict(reviewer_a, "accept"))
        again = live_store.insert_feedback(verdict(reviewer_a, "accept"))
        flipped = live_store.insert_feedback(
            verdict(reviewer_a, "reject", reason="reconsidered")
        )
        other = live_store.insert_feedback(verdict(reviewer_b, "accept"))
        assert (first["state"], again["state"], flipped["state"]) == (
            "created", "unchanged", "replaced",
        )
        assert again["id"] == first["id"] == flipped["id"]
        assert other["state"] == "created" and other["id"] != first["id"]

        rows = live_store.list_feedback(job_id)
        assert len(rows) == 2, f"one row per reviewer, not per POST: {rows}"
        assert {(r["created_by"], r["verdict"]) for r in rows} == {
            (reviewer_a, "reject"), (reviewer_b, "accept"),
        }
        stats = live_store.feedback_stats(job_id)
        assert stats["accepted"] == 1 and stats["rejected"] == 1
        assert stats["acceptance_rate_pct"] == 50.0
    finally:
        with live_store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM finding_feedback WHERE job_id = %s", (job_id,)
            )
            cur.execute("DELETE FROM findings WHERE job_id = %s", (job_id,))
            cur.execute(
                "DELETE FROM verification_jobs WHERE id = %s", (job_id,)
            )


def test_real_mysql_unique_key_exists(live_store: MySQLStore) -> None:
    """0012 landed in this schema — the bound, not just the DAO."""
    config = MySQLConfig.from_env()
    with live_store.connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS cols "
            "FROM information_schema.statistics WHERE table_schema = %s "
            "AND table_name = 'finding_feedback' "
            "AND index_name = 'uniq_feedback_finding_actor'",
            (config.database,),
        )
        row = cur.fetchone()
    assert row is not None and row["cols"] == "finding_id,created_by", (
        "migration 0012 did not apply: acceptance_rate has no bound"
    )
