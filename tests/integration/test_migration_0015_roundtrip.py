"""Migration 0015 round trip on a real MySQL ENUM (Phase 3 follow-up to #298).

The up migration widens ``verification_jobs.status`` from 10 to 15 values.
The risk is not the widening — it is the ROLLBACK:

* narrowing an ENUM while a row holds a value the narrow list does not have
  makes a non-strict MySQL **truncate the row's status to ''** — a silent
  corruption, not a failed statement;
* the down therefore has to FOLD the new states into ones the old list has
  BEFORE it narrows the column.

That fold had never been executed. This test executes it against the real
MySQL engine, on a scratch TABLE with the same ENUM shape, so the shared
``verification_jobs`` table is never narrowed while other tests run.

Honest boundary: this is not a FRESH DATABASE (the test user cannot
CREATE DATABASE — probed, and the answer is recorded here). What it does
cover is the part that can actually break: the ENUM widening, the fold,
the narrowing with a row that held a new value, and the re-widening.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "infra" / "mysql" / "migrations"

#: The ENUM as migration 0002 left it (10 values).
OLD_ENUM = (
    "'PENDING','QUEUED','RUNNING','WAITING_FOR_PROVIDER',"
    "'VERIFIED','BLOCKED','STALE','FAILED','CANCELLED','ERROR'"
)
#: The ENUM as migration 0015 leaves it (15 values).
NEW_ENUM = (
    "'PENDING','QUEUED','RUNNING','WAITING_FOR_PROVIDER',"
    "'VERIFIED','BLOCKED','STALE','FAILED','CANCELLED','ERROR',"
    "'PREPARING','CONTRACT_REVIEW','REVIEWING','NEEDS_REVIEW','EXPIRED'"
)

#: The scratch table the round trip runs on.
PROBE_TABLE = "specproof_mig_0015_probe"


def _connect() -> Any:
    import pymysql

    from storage.mysql import MySQLConfig

    config = MySQLConfig.from_env()
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        autocommit=True,
        charset="utf8mb4",
    )


@pytest.fixture()
def probe_table() -> Any:
    """A scratch table with the pre-0015 ENUM; dropped afterwards."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
    cur.execute(
        f"CREATE TABLE {PROBE_TABLE} ("
        "id VARCHAR(36) PRIMARY KEY, status ENUM(" + OLD_ENUM + ") DEFAULT 'PENDING')"
    )
    try:
        yield conn
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
        conn.close()


def _enum_values(conn: Any) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT COLUMN_TYPE FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = 'status'",
        (PROBE_TABLE,),
    )
    row = cur.fetchone()
    assert row is not None, "the probe table's status column is missing"
    ctype = next(iter(row.values())) if isinstance(row, dict) else row[0]
    inner = ctype[ctype.index("(") + 1 : ctype.rindex(")")]
    return [part.strip().strip("'") for part in inner.split(",")]


def _apply(conn: Any, name: str) -> None:
    """Apply one migration file's statements to the probe table."""
    cur = conn.cursor()
    text = (MIGRATIONS / name).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )
    for raw in code.split(";"):
        stmt = raw.split("-- ", 1)[0].strip()
        if not stmt:
            continue
        # The migrations name the real table; the probe stands in for it.
        stmt = stmt.replace("verification_jobs", PROBE_TABLE)
        cur.execute(stmt)


def test_the_up_migration_widens_the_enum(probe_table: Any) -> None:
    _apply(probe_table, "0015_job_state_vocabulary.sql")
    assert _enum_values(probe_table) == NEW_ENUM.replace("'", "").split(",")


def test_the_down_migration_folds_the_new_states_before_narrowing(
    probe_table: Any,
) -> None:
    """A row holding a NEW value must survive the rollback.

    The down folds PREPARING/CONTRACT_REVIEW/REVIEWING → RUNNING and
    NEEDS_REVIEW/EXPIRED → FAILED first, then narrows. If the fold were
    missing, the narrowing would truncate the row's status to '' —
    corruption, not an error.
    """
    cur = probe_table.cursor()
    _apply(probe_table, "0015_job_state_vocabulary.sql")
    for row_id, status in (
        ("r1", "PREPARING"),
        ("r2", "CONTRACT_REVIEW"),
        ("r3", "REVIEWING"),
        ("r4", "NEEDS_REVIEW"),
        ("r5", "EXPIRED"),
    ):
        cur.execute(
            f"INSERT INTO {PROBE_TABLE} (id, status) VALUES (%s, %s)",
            (row_id, status),
        )

    _apply(probe_table, "down/0015_job_state_vocabulary.sql")

    assert _enum_values(probe_table) == OLD_ENUM.replace("'", "").split(",")
    cur.execute(f"SELECT id, status FROM {PROBE_TABLE} ORDER BY id")
    rows = {
        (r["id"] if isinstance(r, dict) else r[0]): (r["status"] if isinstance(r, dict) else r[1])
        for r in cur.fetchall()
    }
    assert rows == {
        "r1": "RUNNING",
        "r2": "RUNNING",
        "r3": "RUNNING",
        "r4": "FAILED",
        "r5": "FAILED",
    }
    # The decisive claim: no row was truncated to the empty string.
    assert all(value for value in rows.values())


def test_the_round_trip_can_be_run_again(probe_table: Any) -> None:
    """up → down → up must work; the #244 lesson was a pair that did not."""
    _apply(probe_table, "0015_job_state_vocabulary.sql")
    _apply(probe_table, "down/0015_job_state_vocabulary.sql")
    _apply(probe_table, "0015_job_state_vocabulary.sql")
    assert _enum_values(probe_table) == NEW_ENUM.replace("'", "").split(",")

    cur = probe_table.cursor()
    cur.execute(
        f"INSERT INTO {PROBE_TABLE} (id, status) VALUES (%s, %s)",
        ("again", "REVIEWING"),
    )
    cur.execute(f"SELECT status FROM {PROBE_TABLE} WHERE id = 'again'")
    row = cur.fetchone()
    assert row is not None
    assert (row["status"] if isinstance(row, dict) else row[0]) == "REVIEWING"


def test_the_up_migration_is_re_appliable(probe_table: Any) -> None:
    """Applying it twice must not fail — the runner records the version
    only after the statements ran, so a re-apply is a real scenario."""
    _apply(probe_table, "0015_job_state_vocabulary.sql")
    _apply(probe_table, "0015_job_state_vocabulary.sql")
    assert _enum_values(probe_table) == NEW_ENUM.replace("'", "").split(",")
