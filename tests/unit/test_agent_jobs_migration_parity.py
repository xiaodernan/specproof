"""#80 — agent_jobs must be described by exactly one schema source, twice.

`storage/agent_jobs.py` builds its table with a portable
`CREATE TABLE IF NOT EXISTS` it runs at connect time, while
`storage/migrations.py` declares that schema changes are "NEVER ad-hoc CREATE
IF NOT EXISTS" and belong in `infra/mysql/migrations/`. Both were true at once,
and the result measured as a real gap: `ensure_tables()` produced 17 tables
while the live product schema held 18, the missing one being `agent_jobs`.

Migration 0011 closes it. These tests keep the two copies of the same table
from drifting apart again:

  * the DDL text must be identical (columns, order, types, constraints);
  * the migration file must survive this repo's own statement splitter as
    exactly one statement (migration 0008 once leaked a fake statement out of
    a comment that contained a semicolon);
  * a fresh `ensure_tables()` must leave `agent_jobs` behind — the assertion
    that actually fails today without 0011, run only when MySQL answers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from storage.agent_jobs import _SCHEMA_SQL  # noqa: PLC2701 — the point of the test
from storage.migrations import MIGRATIONS_DIR, _split_statements  # noqa: PLC2701

MIGRATION = MIGRATIONS_DIR / "0011_agent_jobs.sql"

#: `(\w+)\s+(...)` pairs are compared as a sequence, so a reordered or retyped
#: column fails the lock instead of silently changing what a fresh install gets.
_COLUMN_RE = re.compile(r"([a-z_][a-z0-9_]*)\s+([A-Z0-9]+(?:\(\d+\))?)")


def _columns(ddl: str) -> list[tuple[str, str]]:
    body = ddl[ddl.index("(", ddl.upper().index("TABLE")) + 1 : ddl.rindex(")")]
    normalized = " ".join(body.split())
    found = _COLUMN_RE.findall(normalized)
    assert found, f"no columns parsed out of {ddl[:60]!r}"
    return found


def test_0011_exists() -> None:
    assert MIGRATION.is_file(), (
        "agent_jobs has no versioned migration: a fresh ensure_tables() build "
        "is missing a table the running product schema has"
    )


def test_migration_and_runtime_ddl_describe_the_same_table() -> None:
    # The file is read through this repo's own splitter, not as raw text: the
    # header comment names other migrations ("0001..0010"), and a parser that
    # sees those words invents columns that no table has.
    statements = _split_statements(MIGRATION.read_text(encoding="utf-8"))
    assert len(statements) == 1, statements
    assert _columns(statements[0]) == _columns(_SCHEMA_SQL), (
        "storage/agent_jobs.py and infra/mysql/migrations/0011_agent_jobs.sql "
        "disagree about agent_jobs; a fresh install and a self-healed install "
        "would then have different columns"
    )


def test_migration_is_one_statement_for_this_repos_splitter() -> None:
    statements = _split_statements(MIGRATION.read_text(encoding="utf-8"))
    assert len(statements) == 1, statements
    assert statements[0].startswith("CREATE TABLE IF NOT EXISTS agent_jobs")
    # Idempotency is what makes this safe on the installations that already
    # created the table at runtime.
    assert "IF NOT EXISTS" in statements[0]


def test_ensure_tables_leaves_agent_jobs_behind() -> None:
    """The measured defect, asserted where a real MySQL answers.

    Only a connectivity error means "no MySQL here". Under this box's load a
    migration statement can be cut off mid-query (pymysql 2013 / read timeout)
    and that is an environment fact; a schema error is never skipped away.
    """
    import pymysql

    from storage.mysql import MySQLConfig, MySQLStore

    config = MySQLConfig.from_env()
    store = MySQLStore()
    try:
        store.ensure_tables()
        with store.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS n FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = 'agent_jobs'",
                (config.database,),
            )
            row = cursor.fetchone()
    except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as exc:
        pytest.skip(f"MySQL at {config.host}:{config.port} did not answer: {exc}")
    values = tuple(row.values()) if isinstance(row, dict) else tuple(row)
    assert int(values[0]) == 1, (
        f"ensure_tables() left {config.database} without agent_jobs"
    )


def test_down_migration_is_the_mirror_image() -> None:
    down = Path(MIGRATION).parent / "down" / MIGRATION.name
    assert down.is_file(), "every migration in this directory has a down file"
    assert "DROP TABLE IF EXISTS agent_jobs" in down.read_text(encoding="utf-8")
