"""Versioned schema migrations (P0-B1).

Schema changes are NEVER ad-hoc CREATE IF NOT EXISTS. Every change is a
numbered .sql file under infra/mysql/migrations, applied exactly once in
order and recorded in schema_migrations. This gives enterprises the two
things a production database needs: reproducible bootstrap and an audit
trail of what changed when.

ensure_tables() on MySQLStore delegates here for backward compatibility.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from storage.mysql import MySQLStore

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "infra" / "mysql" / "migrations"


class MigrationError(Exception):
    """Raised when a migration cannot be applied."""


def _split_statements(sql: str) -> list[str]:
    """Drop comment LINES first, then split on ';'.

    Comment stripping must run BEFORE the ';' split: a comment line that
    itself contains a semicolon (migration 0008: "--   next_retry_at ...
    deferral; the relay only claims rows") would otherwise leak its
    post-semicolon text into a fake statement — observed live when 0008
    failed to apply on the dev database. A leading "-- 0002: ..." comment
    block must also not swallow the ALTER that follows it (the old
    segment-wise version silently dropped the 0002 enum ALTER).
    """
    code_lines = [
        ln for ln in sql.splitlines() if not ln.strip().startswith("--")
    ]
    statements: list[str] = []
    for raw in "\n".join(code_lines).split(";"):
        stmt = raw.split("-- ", 1)[0].strip()
        if stmt:
            statements.append(stmt)
    return statements


class MigrationRunner:
    """Applies pending migrations in filename order."""

    def __init__(self, store: MySQLStore | None = None) -> None:
        self.store = store or MySQLStore()

    def ensure_schema_migrations(self) -> None:
        with self.store.connection() as conn:
            conn.cursor().execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INT PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL, "
                "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            )

    def applied_versions(self) -> set[int]:
        self.ensure_schema_migrations()
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version FROM schema_migrations")
            rows = cur.fetchall()
        return {int(r["version"]) for r in rows}

    def migration_files(self) -> list[tuple[int, str, Path]]:
        if not MIGRATIONS_DIR.exists():
            return []
        files: list[tuple[int, str, Path]] = []
        for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
            parts = p.name.split("_", 1)
            try:
                version = int(parts[0])
            except ValueError:
                raise MigrationError(
                    "Migration filename must start with a number: " + p.name
                ) from None
            files.append((version, parts[1], p))
        return files

    def apply_pending(self) -> list[str]:
        """Apply every not-yet-applied migration. Returns applied names."""
        applied: list[str] = []
        done = self.applied_versions()
        for version, name, path in self.migration_files():
            if version in done:
                continue
            sql = path.read_text(encoding="utf-8")
            statements = _split_statements(sql)
            # One migration = one transaction: either fully applied or not.
            with self.store.connection() as conn:
                for stmt in statements:
                    conn.cursor().execute(stmt)
                conn.cursor().execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                    (version, name),
                )
            applied.append(name)
            logger.info("Applied migration %04d %s", version, name)
        return applied

    def status(self) -> dict[str, Any]:
        """Human-readable migration status."""
        done = self.applied_versions()
        files = self.migration_files()
        return {
            "applied": [n for v, n, _ in files if v in done],
            "pending": [n for v, n, _ in files if v not in done],
        }
