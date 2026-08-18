"""P0-B1 tests — versioned migration runner (comment-safe splitting)."""


import pytest

from storage.migrations import MigrationRunner, _split_statements


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
