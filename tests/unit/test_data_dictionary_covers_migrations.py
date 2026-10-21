"""#80's other half: the data dictionary must keep up with the migrations.

`docs/architecture/DATA_DICTIONARY.md` opens by promising a field-level register
of "all persisted state", and names the versioned migrations as the source of
truth for the MySQL schema. Measured on 2026-09-26, that promise was false in
three ways at once:

  * it named `0001..0008` as the whole range while 0009 and 0010 had long
    landed — so `finding_feedback` existed in both live schemas and had no
    entry in the document at all;
  * it counted 19 tables, and listed two (`object_metadata`, `object_contracts`)
    that neither real schema contains, because those belong to an opt-in MySQL
    backend whose default is SQLite;
  * `agent_jobs` was registered as "code DDL", which is exactly the framing
    migration 0011 removed.

The #80 parity test keeps the two copies of one table's DDL honest; this file
keeps the document honest, so the next migration cannot land without an entry.
Only the last test needs a database; the rest are text-only and run anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from storage.migrations import MIGRATIONS_DIR, _split_statements  # noqa: PLC2701

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DICTIONARY = REPO_ROOT / "docs" / "architecture" / "DATA_DICTIONARY.md"

_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)

#: §1's entries are "### 1.<n> <table> — …"; a table counts as registered only
#: when it owns such a heading. A stray mention in prose would let an
#: undocumented table pass, which is the mistake this gate exists to catch.
_SECTION_RE = re.compile(r"^### 1\.\d+ ([a-z_][a-z0-9_]*)", re.MULTILINE)

#: The header's stated range end: "以 `…0001_init.sql` 至 `0011_agent_jobs.sql` …".
_RANGE_RE = re.compile(r"至\s*`([0-9]{4}_[a-z_]+\.sql)`")

#: §1.18 must state the absence itself, not merely name a backend — a section
#: that mentions SQLite in passing while still listing the tables under MySQL
#: is the lie that was measured here.
_ABSENT_RE = re.compile(r"没有这两张表")

#: The object-metadata tables exist only where the MySQL object-metadata
#: backend was used (the default backend is SQLite). They are documented
#: but they are not part of the always-present schema, so the table-count
#: gate subtracts the ones actually in front of it.
_CONDITIONAL_TABLES: frozenset[str] = frozenset(
    {"object_metadata", "object_contracts"}
)


def _registered_tables(doc: str) -> set[str]:
    return set(_SECTION_RE.findall(doc))



def _created_tables() -> dict[str, list[str]]:
    """migration file -> tables it creates, read through the repo's splitter."""
    created: dict[str, list[str]] = {}
    for sql in sorted(MIGRATIONS_DIR.glob("*.sql")):
        tables: list[str] = []
        for statement in _split_statements(sql.read_text(encoding="utf-8")):
            if statement.lstrip().upper().startswith("CREATE TABLE"):
                found = _TABLE_RE.match(statement.lstrip())
                assert found is not None, statement[:60]
                tables.append(found.group(1))
        created[sql.name] = tables
    assert created, f"no migration found under {MIGRATIONS_DIR}"
    assert any(tables for tables in created.values()), "no migration creates a table"
    return created


def _doc() -> str:
    return DATA_DICTIONARY.read_text(encoding="utf-8")


def test_every_table_a_migration_creates_has_a_data_dictionary_entry() -> None:
    registered = _registered_tables(_doc())
    missing = [
        f"{name}: {table}"
        for name, tables in _created_tables().items()
        for table in tables
        if table not in registered
    ]
    assert not missing, (
        "DATA_DICTIONARY.md claims to register every persisted table, but "
        f"these migration tables own no §1 entry: {missing}"
    )


def test_data_dictionary_names_the_newest_migration_in_its_range() -> None:
    newest = max(MIGRATIONS_DIR.glob("*.sql")).name
    stated = _RANGE_RE.search(_doc())
    assert stated is not None, (
        "the document no longer states which migration its schema follows"
    )
    assert stated.group(1) == newest, (
        f"the document's range ends at {stated.group(1)} but the newest "
        f"migration is {newest}; a reader would conclude the schema is "
        "older than it is"
    )


def test_agent_jobs_is_no_longer_documented_as_code_only_ddl() -> None:
    heading = _heading("### 1.17 agent_jobs")
    assert "0011" in heading, (
        "agent_jobs is still attributed to code DDL alone; 0011 made it a "
        "versioned migration and the entry must say which copy is authoritative"
    )


def test_conditional_object_tables_are_flagged_as_absent_by_default() -> None:
    doc = _doc()
    section = doc[doc.index("### 1.18 object_metadata") : doc.index("## 2.")]
    assert _ABSENT_RE.search(section), (
        "object_metadata/object_contracts are documented under MySQL, but "
        "default_object_metadata_store() returns SQLite and neither real "
        "schema contains them — the entry has to state that absence, not "
        "just mention some backend"
    )


def test_documented_table_count_matches_the_live_schema() -> None:
    """The 17-vs-18 mistake, asserted where a real MySQL answers."""
    claim = re.search(r"共 (\d+) 张表", _doc())
    assert claim is not None, "the document no longer states a table count"
    documented = int(claim.group(1))

    from storage.mysql import MySQLConfig, MySQLStore

    config = MySQLConfig.from_env()
    store = MySQLStore()
    try:
        with store.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                # LOWER(): information_schema's column names come back
                # UPPERCASE on MySQL 8, and a row["table_name"] would
                # raise KeyError — which the skip below would report as
                # "MySQL is not reachable", i.e. a lie about why.
                "SELECT LOWER(table_name) AS table_name "
                "FROM information_schema.tables "
                "WHERE table_schema = %s",
                (config.database,),
            )
            names = {
                str(row["table_name"]) if isinstance(row, dict) else str(row[0])
                for row in cursor.fetchall()
            }
    except Exception as exc:  # noqa: BLE001 — no MySQL here is a coverage fact
        pytest.skip(
            f"MySQL at {config.host}:{config.port} is not usable here "
            f"({type(exc).__name__}: {exc})"
        )

    # The object-metadata tables are CONDITIONAL: the default backend is
    # SQLite, so they exist only where the MySQL object-metadata backend
    # was used. They are documented (§1.18/§1.19) but they are not part
    # of the always-present schema, so the count subtracts the ones that
    # are actually in front of it — otherwise the gate would depend on
    # whether some other test ran first.
    conditional = _CONDITIONAL_TABLES & names
    present = len(names) - len(conditional)
    assert documented == present, (
        f"DATA_DICTIONARY says {documented} tables, {config.database} has "
        f"{present} ({len(conditional)} conditional object tables excluded: "
        f"{sorted(conditional)})"
    )


def _heading(prefix: str) -> str:
    doc = _doc()
    assert prefix in doc, f"{prefix} is gone from DATA_DICTIONARY.md"
    return doc[doc.index(prefix) :].splitlines()[0]
