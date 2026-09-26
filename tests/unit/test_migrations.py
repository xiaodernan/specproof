"""P0-B1 tests — versioned migration runner (comment-safe splitting)."""


import contextlib
import logging

import pymysql
import pytest

from storage.migrations import MigrationRunner, _split_statements


class _Cursor:
    def __init__(self, log: list[str], fail_on: tuple[str, int] | None) -> None:
        self._log = log
        self._fail = fail_on

    def execute(self, sql, args=None):
        self._log.append(sql)
        if self._fail and self._fail[0] in sql:
            raise pymysql.err.OperationalError(self._fail[1], "injected")

    def fetchall(self):
        return []


class _Conn:
    def __init__(self, log: list[str], fail_on: tuple[str, int] | None) -> None:
        self._cursor = _Cursor(log, fail_on)

    def cursor(self):
        return self._cursor


class FakeStore:
    """Records every statement the runner sends, optionally failing one."""

    def __init__(self, fail_on: tuple[str, int] | None = None) -> None:
        self.log: list[str] = []
        self._fail = fail_on

    @contextlib.contextmanager
    def connection(self):
        yield _Conn(self.log, self._fail)


def _migration_file(tmp_path, monkeypatch, sql: str) -> None:
    monkeypatch.setattr("storage.migrations.MIGRATIONS_DIR", tmp_path)
    (tmp_path / "0002_add_index.sql").write_text(sql, encoding="utf-8")


def test_split_keeps_statement_after_comment_lines():
    sql = (
        "-- 0002: comment line\n"
        "-- more comment\n"
        "ALTER TABLE t MODIFY c ENUM('A','B');\n\n"
        "CREATE TABLE IF NOT EXISTS x (id INT);"
    )
    stmts = _split_statements(sql)
    assert len(stmts) == 2
    assert stmts[0].startswith("ALTER TABLE")
    assert "CREATE TABLE" in stmts[1]


def test_split_drops_empty_and_comment_only():
    sql = ";; -- just a comment\n;"
    assert _split_statements(sql) == []


@pytest.mark.integration
def test_apply_pending_records_versions():
    """Against live MySQL: applying twice is idempotent (skip-safe)."""
    from storage.mysql import MySQLStore

    store = MySQLStore()
    try:
        store.ensure_tables()
    except Exception:
        pytest.skip("MySQL not available")
    runner = MigrationRunner(store)
    status = runner.status()
    assert status["pending"] == []  # already applied by ensure_tables
    # Applying again must be a no-op (versions recorded).
    assert runner.apply_pending() == []


def test_bad_migration_filename_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "storage.migrations.MIGRATIONS_DIR", tmp_path
    )
    (tmp_path / "notanumber_x.sql").write_text("SELECT 1;", encoding="utf-8")
    from storage.migrations import MigrationError

    runner = MigrationRunner()
    with pytest.raises(MigrationError):
        runner.migration_files()


# ── re-appliability: MySQL commits DDL implicitly, so a half-applied
#    migration must converge on a second run (measured on 0012, 2026-09-26) ──


_MIXED = "DELETE FROM finding_feedback WHERE 1=0;\n" + (
    "ALTER TABLE finding_feedback\n"
    "ADD UNIQUE KEY uniq_actor (finding_id, created_by);\n"
)


@pytest.mark.parametrize("errno", [1050, 1060, 1061], ids=[
    "table exists", "duplicate column", "duplicate key name",
])
def test_already_applied_ddl_does_not_block_recording(tmp_path, monkeypatch, caplog, errno):
    """The statement says "already there" -> finish the migration, loudly."""
    _migration_file(tmp_path, monkeypatch, _MIXED)
    store = FakeStore(fail_on=("ALTER TABLE", errno))
    with caplog.at_level(logging.WARNING, logger="storage.migrations"):
        assert MigrationRunner(store).apply_pending() == ["add_index.sql"]
    assert any(
        s.startswith("INSERT INTO schema_migrations") for s in store.log
    ), "the version row is what makes the next boot skip this migration"
    assert str(errno) in caplog.text
    assert "0002" in caplog.text, "the warning must name the migration"


@pytest.mark.parametrize("errno", [1064, 1062, 1146], ids=[
    "syntax", "duplicate entry", "table missing",
])
def test_any_other_error_still_aborts(tmp_path, monkeypatch, errno):
    """Tolerance is an allow-list, not a swallow.

    1062 matters most: that is the dedupe step failing to make the data
    unique, and pretending otherwise would record a migration that did
    not happen.
    """
    _migration_file(tmp_path, monkeypatch, _MIXED)
    store = FakeStore(fail_on=("ALTER TABLE", errno))
    with pytest.raises(pymysql.err.OperationalError):
        MigrationRunner(store).apply_pending()
    assert not any(
        s.startswith("INSERT INTO schema_migrations") for s in store.log
    ), f"MySQL {errno} is not an idempotency signal; never record the version"
