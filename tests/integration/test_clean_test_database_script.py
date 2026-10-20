"""Gates for the test-database hygiene script (scripts/clean_test_database.py).

The script exists because the test schema accumulates tables that the
schema does not own — a mutation arm's probe that did not clean up
after itself (measured 2026-10-20: `arm_probe`, eight days old). The
residue is not cosmetic: the data dictionary's gate compares the
DOCUMENTED table count against the LIVE one, so a leftover table makes
a real gate fail for a reason that has nothing to do with the schema.

These gates pin the two things that matter about a tool that drops
tables:

* it CANNOT be pointed at the product schema (the refusal is the
  safety property, not the naming convention);
* the expected set is DERIVED from the migrations, and a table that
  only appears in a migration COMMENT is not mistaken for a real one.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "clean_test_database.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("clean_test_database", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cleaner() -> Any:
    return _load()


class TestTheGuard:
    def test_the_product_schema_is_refused(self, cleaner: Any) -> None:
        """Exit 2, and NOTHING is connected to."""
        assert cleaner.main(["--database", "specproof_phase0"]) == 2

    def test_any_other_schema_is_refused_too(self, cleaner: Any) -> None:
        """Not just the product schema — only specproof_test* is allowed."""
        for database in ("production", "specproof", "test", "specproof_phase0_test"):
            assert cleaner.main(["--database", database]) == 2, database

    def test_the_test_schema_is_allowed(self, cleaner: Any) -> None:
        assert cleaner.ALLOWED_DATABASE_PATTERN.match("specproof_test")
        assert cleaner.ALLOWED_DATABASE_PATTERN.match("specproof_test_2")
        assert not cleaner.ALLOWED_DATABASE_PATTERN.match("specproof_phase0")


class TestTheOwnedSet:
    def test_it_is_derived_from_the_migrations(self, cleaner: Any) -> None:
        owned = cleaner.owned_tables()
        for table in (
            "verification_jobs", "findings", "contracts", "outbox",
            "audit_logs", "tenants", "users", "api_tokens", "invoices",
            "usage_ledger", "finding_feedback", "notify_outbox",
            "agent_jobs", "schema_migrations",
        ):
            assert table in owned, table

    def test_a_table_mentioned_only_in_a_comment_is_not_owned(self) -> None:
        """Two migrations mention CREATE TABLE in a comment.

        `0011` says "runtime `CREATE TABLE IF NOT EXISTS` in
        storage/agent_jobs.py" and `0014` says "storage/billing.py's
        CREATE TABLE covers fresh ones". Reading the comments as DDL
        would add two tables that do not exist — and the report would
        then call the real ones "missing".
        """
        module = _load()
        owned = module.owned_tables()
        assert "IF" not in owned
        assert "covers" not in owned
        assert all(table.islower() for table in owned), sorted(owned)

    def test_the_code_ddl_table_is_included(self, cleaner: Any) -> None:
        """schema_migrations is created by code, not by a migration."""
        assert "schema_migrations" in cleaner.owned_tables()


class TestTheCleanCycle:
    def _seed_residue(self) -> str:
        import pymysql

        from storage.mysql import MySQLConfig

        config = MySQLConfig.from_env()
        name = f"residue_{uuid.uuid4().hex[:8]}"
        conn = pymysql.connect(
            host=config.host, port=config.port, user=config.user,
            password=config.password, database=config.database,
            autocommit=True, charset="utf8mb4",
        )
        cur = conn.cursor()
        cur.execute(f"CREATE TABLE `{name}` (id INT PRIMARY KEY)")
        conn.close()
        return name

    def _tables(self) -> list[str]:
        import pymysql

        from storage.mysql import MySQLConfig

        config = MySQLConfig.from_env()
        conn = pymysql.connect(
            host=config.host, port=config.port, user=config.user,
            password=config.password, database=config.database,
            autocommit=True, charset="utf8mb4",
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.tables "
            "WHERE table_schema = DATABASE() ORDER BY TABLE_NAME"
        )
        names = [str(row[0]) for row in cur.fetchall()]
        conn.close()
        return names

    def test_the_report_mode_finds_the_residue_and_changes_nothing(
        self, cleaner: Any,
    ) -> None:
        name = self._seed_residue()
        try:
            assert cleaner.main([]) == 0
            # Still there: the default is a report.
            assert name in self._tables()
        finally:
            import pymysql

            from storage.mysql import MySQLConfig

            config = MySQLConfig.from_env()
            conn = pymysql.connect(
                host=config.host, port=config.port, user=config.user,
                password=config.password, database=config.database,
                autocommit=True, charset="utf8mb4",
            )
            conn.cursor().execute(f"DROP TABLE IF EXISTS `{name}`")
            conn.close()

    def test_the_drop_mode_removes_the_residue(self, cleaner: Any) -> None:
        name = self._seed_residue()
        try:
            assert cleaner.main(["--drop"]) == 0
            assert name not in self._tables()
        finally:
            import pymysql

            from storage.mysql import MySQLConfig

            config = MySQLConfig.from_env()
            conn = pymysql.connect(
                host=config.host, port=config.port, user=config.user,
                password=config.password, database=config.database,
                autocommit=True, charset="utf8mb4",
            )
            conn.cursor().execute(f"DROP TABLE IF EXISTS `{name}`")
            conn.close()

    def test_a_clean_schema_reports_no_residue(self, cleaner: Any) -> None:
        assert cleaner.main([]) == 0
