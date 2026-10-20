"""Clean the TEST database of tables the schema does not own.

Why this exists
---------------
The test schema (``specproof_test``) is shared by every DB-backed test
and by the mutation batteries. A probe that creates a table and does not
drop it leaves the schema permanently larger than the product schema —
and the data dictionary's gate (``test_data_dictionary_covers_migrations``)
compares the DOCUMENTED table count against the LIVE one. Measured
2026-10-20: the test schema held 20 tables while the product schema held
19; the extra one was ``arm_probe``, a mutation arm's leftover from
2026-10-12.

So the residue is not cosmetic: it makes a real gate fail for a reason
that has nothing to do with the schema, and it hides the difference
between "the schema grew" and "something left a table behind".

What it does
------------
1. Computes the tables the schema OWNS, from the versioned migrations
   (every ``CREATE TABLE``) plus the one code-DDL table the migrations
   do not create (``schema_migrations``). The expected set is therefore
   derived from the source of truth, not hardcoded here.
2. Lists the tables that are present but NOT owned — the residue.
3. With ``--drop``, drops them.

Safety
------
* It refuses any target whose name is not ``specproof_test*``. The
  product schema (``specproof_phase0``) can never be the target.
* Without ``--drop`` it changes nothing: the default is a report.
* It only ever issues ``DROP TABLE`` on names it has just listed as
  residue, in a schema whose name passed the guard.

    python scripts/clean_test_database.py             # report only
    python scripts/clean_test_database.py --drop      # report and drop
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "infra" / "mysql" / "migrations"

#: The schema this script is allowed to touch. The product schema is
#: ``specproof_phase0`` and is NOT in this pattern — pointing the tool
#: at production has to fail, not be a matter of care.
ALLOWED_DATABASE_PATTERN = re.compile(r"^specproof_test[A-Za-z0-9_]*$")

#: The product schema's name, named here so the refusal message can say
#: what it is protecting.
PRODUCT_DATABASE = "specproof_phase0"

#: The tables the migrations do NOT create but the schema owns. Each one
#: is created by code DDL on an existing installation (the data
#: dictionary registers them as such).
CODE_DDL_TABLES = ("schema_migrations",)

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?",
    re.IGNORECASE,
)


def owned_tables() -> set[str]:
    """The tables the schema owns, derived from the migrations.

    The comment lines are stripped FIRST — the same thing the migration
    runner does before it splits statements. Without that, a comment
    that merely MENTIONS ``CREATE TABLE`` (two migrations do) would add
    a table that does not exist, and the residue report would call a
    real table "missing".
    """
    owned: set[str] = set(CODE_DDL_TABLES)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("--")
        )
        for match in _CREATE_TABLE_RE.finditer(code):
            owned.add(match.group(1))
    return owned


def connect(database: str) -> object:
    import pymysql

    from storage.mysql import MySQLConfig

    config = MySQLConfig.from_env()
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=database,
        autocommit=True,
        charset="utf8mb4",
    )


def live_tables(conn: object) -> list[str]:
    cur = conn.cursor()  # type: ignore[attr-defined]
    cur.execute(
        "SELECT TABLE_NAME FROM information_schema.tables "
        "WHERE table_schema = DATABASE() ORDER BY TABLE_NAME"
    )
    return [str(row[0]) for row in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default=os.getenv("MYSQL_DATABASE", "specproof_test"),
        help="the test schema to clean (must match specproof_test*)",
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="actually drop the residue (without it, the script only reports)",
    )
    args = parser.parse_args(argv)

    database = str(args.database)
    if not ALLOWED_DATABASE_PATTERN.match(database):
        print(
            f"ABORT: --database must match {ALLOWED_DATABASE_PATTERN.pattern} "
            f"(got {database!r}). This tool never touches the product "
            f"schema ({PRODUCT_DATABASE}) or any other schema.",
            file=sys.stderr,
        )
        return 2

    expected = owned_tables()
    try:
        conn = connect(database)
    except Exception as exc:  # noqa: BLE001 — the operator needs the reason
        print(f"ABORT: cannot connect to {database!r}: {exc}", file=sys.stderr)
        return 2

    try:
        present = live_tables(conn)
        residue = [name for name in present if name not in expected]
        missing = sorted(name for name in expected if name not in present)

        print(f"database: {database}")
        print(f"tables present: {len(present)}")
        print(f"tables the schema owns: {len(expected)}")
        if missing:
            print(
                f"WARNING: {len(missing)} owned table(s) are missing: "
                + ", ".join(missing)
            )
            print("         run the migrations before trusting this report")
        if not residue:
            print("residue: none — the schema holds only its own tables")
            return 0

        print(f"residue: {len(residue)} table(s) the schema does not own:")
        for name in residue:
            print(f"  - {name}")
        if not args.drop:
            print("\n(report only — re-run with --drop to remove them)")
            return 0
        cur = conn.cursor()  # type: ignore[attr-defined]
        for name in residue:
            cur.execute(f"DROP TABLE IF EXISTS `{name}`")
            print(f"dropped: {name}")
        print(f"\ndropped {len(residue)} table(s)")
        return 0
    finally:
        conn.close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    raise SystemExit(main())
