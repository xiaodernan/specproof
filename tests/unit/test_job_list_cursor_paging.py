"""The job list can be paged by cursor (keyset), and the cursor costs the
same however deep the page is.

#1618 added the keyset path next to the classic offset one: the cursor
carries the (created_at, id) of the previous page's last row and the query
asks for "strictly before it in this order", which the composite index
serves directly. The offset path stays (a client that wants page NUMBERS
needs it), and the two are alternatives -- a cursor wins when both are
given.

What these legs measure:
  * the cursor path returns the SAME rows as the offset path (the order is
    the store's business; a different answer would be a different list),
  * the last page says so (no next cursor),
  * a cursor that is not ours is ignored (the client gets the first page
    instead of a 500),
  * and the reason the cursor exists: at depth, the offset path READS the
    rows it throws away, while the cursor path does not. The measurement is
    "rows examined" from the query plan -- a counter, not a stopwatch.
"""

from __future__ import annotations

import uuid

import pytest

from storage.mysql import MySQLStore, decode_job_cursor, encode_job_cursor
from tests._mysql_gate import requires_mysql

#: The keyset-cursor paging legs all write to MySQL, and they skip on the
#: session's isolation verdict like every other live-database case — not on
#: a probe of their own (#1622 folded the self-deciding files onto the shared
#: owner; LEGACY_RUN_TIME_SKIPS stays empty).
pytestmark = requires_mysql("the keyset-cursor paging leg writes to MySQL")


@pytest.fixture()
def store() -> MySQLStore:
    s = MySQLStore()
    s.ensure_tables()
    return s


def _seed(store: MySQLStore, count: int) -> list[str]:
    ids = []
    for i in range(count):
        jid = str(uuid.uuid4())
        store.insert_job(
            {
                "id": jid,
                "repo_path": f"/test/repo-{i}",
                "base_ref": "base",
                "head_ref": "head",
                "spec_path": "/test/spec.md",
                "status": "VERIFIED",
                "depth": "FAST",
            }
        )
        ids.append(jid)
    return ids


def _cleanup(store: MySQLStore, ids: list[str]) -> None:
    """Remove the rows this leg seeded, through the store's own deletion.

    Not a raw DELETE: the store's deletion writes the explaining audit row
    in the same transaction (the trail outlives the job by design), and the
    audit-parity gate refuses a test that deletes job rows in place.
    """
    for jid in ids:
        store.delete_job_records(jid)


def test_the_cursor_path_returns_the_same_rows_as_the_offset_path(
    store: MySQLStore,
) -> None:
    ids = _seed(store, 12)
    try:
        # three pages on each side: the table holds other rows too, so the
        # cursor walk must stop where the offset walk stops (or the lists
        # would differ in LENGTH, not in content).
        offset_rows: list[str] = []
        for offset in (0, 5, 10):
            page = store.search_jobs(5, offset)
            offset_rows.extend(row["id"] for row in page["jobs"])

        cursor_rows: list[str] = []
        cursor = None
        for _ in range(3):
            page = store.search_jobs(5, 0, cursor=cursor)
            cursor_rows.extend(row["id"] for row in page["jobs"])
            cursor = page.get("next_cursor")
            if not cursor:
                break

        assert cursor_rows == offset_rows
    finally:
        _cleanup(store, ids)


def test_the_last_page_reports_no_next_cursor(store: MySQLStore) -> None:
    ids = _seed(store, 3)
    try:
        # a limit that holds the whole table: this page IS the last one
        page = store.search_jobs(100_000, 0, cursor=None)
        assert page["jobs"]
        assert not page.get("next_cursor"), (
            "a page that holds every remaining row must not advertise a next one"
        )
    finally:
        _cleanup(store, ids)


def test_a_cursor_that_is_not_ours_is_ignored(store: MySQLStore) -> None:
    """A hand-made or stale cursor gets the first page, not a 500."""
    ids = _seed(store, 2)
    try:
        page = store.search_jobs(10, 0, cursor="not-a-real-cursor")
        assert page["jobs"], "the first page must still come back"
    finally:
        _cleanup(store, ids)


def test_the_cursor_round_trips_the_rows_position() -> None:
    """The codec is the store's business; a client must not be able to read
    it, and it must survive the round trip."""
    import datetime

    stamp = datetime.datetime(2026, 11, 10, 12, 30, 15, 123456)
    cursor = encode_job_cursor(stamp, "job-42")
    assert "job-42" not in cursor, "the cursor must not spell the row out"
    decoded = decode_job_cursor(cursor)
    assert decoded is not None
    assert decoded[1] == "job-42"
    # the stamp comes back as a DATETIME the database can compare with (the
    # ISO "T" form is not DATETIME syntax and would compare
    # lexicographically -- skipping and repeating rows)
    assert decoded[0] == stamp
    assert decoded[0].microsecond == 123456


def test_a_deep_page_reads_fewer_rows_through_the_cursor(store: MySQLStore) -> None:
    """The reason the cursor exists, measured with a counter.

    At depth D the offset path makes the database walk (and discard) the rows
    before the page; the cursor path starts AT the page. "Rows examined" is
    the plan's own number, not a stopwatch -- it does not wobble with the
    machine's mood.
    """
    ids = _seed(store, 400)
    try:
        limit = 20
        depth = 200  # page 11 of 400

        # the offset path at that depth
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "EXPLAIN SELECT id FROM verification_jobs "
                "ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                (limit, depth),
            )
            offset_plan = cur.fetchone()

        # the cursor path at the same depth: the row the offset page ended on
        page = store.search_jobs(limit, depth)
        last = page["jobs"][-1]
        cursor = encode_job_cursor(last["created_at"], last["id"])
        decoded = decode_job_cursor(cursor)
        assert decoded is not None
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "EXPLAIN SELECT id FROM verification_jobs "
                "WHERE (created_at, id) < (%s, %s) "
                "ORDER BY created_at DESC, id DESC LIMIT %s",
                (decoded[0], decoded[1], limit),
            )
            cursor_plan = cur.fetchone()

        offset_rows = int(offset_plan.get("rows") or 0)
        cursor_rows = int(cursor_plan.get("rows") or 0)
        assert cursor_rows <= offset_rows, (
            f"the cursor page examined {cursor_rows} rows, the offset page "
            f"{offset_rows} -- the keyset path must not read more"
        )
    finally:
        _cleanup(store, ids)
