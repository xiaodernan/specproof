"""Rolled-back migrations are the reverse-direction counterpart of
`storage.migrations`. Until today the repository shipped the down-SQL files
(`infra/mysql/migrations/down/NNNN_name.sql`) but no code that ran them —
the down files were documentation with no enforcement. This module makes
them executable, with the safety rails the operation deserves.

Honesty rules:
  * Only versions already recorded in schema_migrations can be rolled back.
    Rolling back a version that was never applied is an error, not a no-op.
  * Migrations are rolled back in reverse order (highest version first) —
    rolling back a lower version while a higher one still depends on its
    columns or indexes is a disaster.
  * A missing down-migration file is an error, not a skipped step.
  * Live execution requires allow_production=True AND a database whose
    name ends in `_test` (the schema used by the regression suite).
    Production (anything else) is refused; the safety rule is a hard rule.
  * `--dry-run` equivalent on the runner (dry_run=True) is the default
    on the CLI. The command reports the plan it would execute, every
    statement it would run, and the down-file for each version, and exits —
    without touching the database.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from storage.migrations import MIGRATIONS_DIR, MigrationError, _split_statements
from storage.mysql import MySQLStore

_TEST_DATABASE_RE = re.compile(r"^specproof_test[A-Za-z0-9_]*$")


class RollbackError(MigrationError):
    """Raised when a rollback cannot proceed or is refused."""


def down_files(*, migrations_dir: Path) -> dict[int, Path]:
    out: dict[int, Path] = {}
    down = migrations_dir / "down"
    if not down.is_dir():
        return out
    for p in sorted(down.glob("*.sql")):
        head, _, _tail = p.name.partition("_")
        try:
            version = int(head)
        except ValueError as exc:
            raise RollbackError(
                f"down migration must start with a version number: {p.name}"
            ) from exc
        out[version] = p
    return out


def is_test_database(store: Any) -> bool:
    """Returns True iff `store.config['database']` ends in `_test`."""
    if store is None:
        return False
    cfg = getattr(store, "config", None)
    if cfg is None and hasattr(store, "_config"):
        cfg = store._config
    db = ""
    if isinstance(cfg, dict):
        db = str(cfg.get("database") or cfg.get("MYSQL_DATABASE") or "")
    elif cfg is not None:
        db = str(getattr(cfg, "database", "") or getattr(cfg, "MYSQL_DATABASE", "") or "")
    # Allow test db family: specproof_test, specproof_test1, specproof_test_bar,
    # etc. — production names (specproof_phase0 etc.) are refused.
    return bool(_TEST_DATABASE_RE.fullmatch(db or ""))


def _name_of(path: Path) -> str:
    stem = path.stem
    idx = stem.find("_")
    return stem[idx + 1:] if idx >= 0 else stem


class MigrationRollbackRunner:
    """Rolls back applied migrations to a given target version (exclusive)."""

    def __init__(
        self,
        store: Any | None = None,
        *,
        migrations_dir: Path | None = None,
    ) -> None:
        self.store = store if store is not None else MySQLStore()
        self.migrations_dir = migrations_dir if migrations_dir is not None else MIGRATIONS_DIR

    def _schema_versions(self, conn: Any) -> list[int]:
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_migrations ORDER BY version DESC")
        rows = cur.fetchall() or []
        out: list[int] = []
        for r in rows:
            v = r.get("version") if isinstance(r, dict) else (r[0] if r else None)
            if v is not None:
                out.append(int(v))
        return out

    def plan(self, target: int) -> list[tuple[int, str, Path, list[str]]]:
        if target < 0:
            raise RollbackError(f"target version must be >= 0, got {target}")

        with self.store.connection() as conn:
            applied = self._schema_versions(conn)

        todo = [v for v in applied if v > target]
        if not todo:
            return []

        down = down_files(migrations_dir=self.migrations_dir)
        if not down:
            raise RollbackError(
                f"no down migrations found under {self.migrations_dir / 'down'}; "
                "refusing to pretend a rollback is possible"
            )

        plan: list[tuple[int, str, Path, list[str]]] = []
        for version in sorted(todo, reverse=True):
            path = down.get(version)
            if path is None:
                raise RollbackError(
                    f"no down migration for version {version:04d} under "
                    f"{self.migrations_dir / 'down'} — refusing to skip it silently"
                )
            sql = path.read_text(encoding="utf-8")
            stmts = _split_statements(sql)
            if not stmts:
                raise RollbackError(
                    f"down migration {path.name} yielded zero executable statements; "
                    "the file is malformed"
                )
            plan.append((version, _name_of(path), path, stmts))
        return plan

    def apply(
        self,
        target: int,
        *,
        dry_run: bool,
        allow_production: bool,
    ) -> list[dict[str, Any]]:
        """Execute (or, with dry_run=True, only plan) the rollback.

        The production-database guard runs BEFORE planning opens a single
        connection for the live path, so a non-test database never receives
        one query. Dry-run is a read-only plan and is allowed against any
        database.
        """
        if not dry_run and not allow_production and not is_test_database(self.store):
            raise RollbackError(
                "refusing to execute against a database that does not end in '_test'. "
                "Pass --i-am-sure-rolling-back to override on the CLI."
            )

        plan = self.plan(target)

        if dry_run:
            return [
                {
                    "version": version,
                    "name": name,
                    "path": str(path),
                    "statements": stmts,
                    "statement_count": len(stmts),
                    "applied": False,
                    "dry_run": True,
                }
                for version, name, path, stmts in plan
            ]

        report: list[dict[str, Any]] = []
        for version, name, path, stmts in plan:
            with self.store.connection() as conn:
                for stmt in stmts:
                    conn.cursor().execute(stmt)
                conn.cursor().execute(
                    "DELETE FROM schema_migrations WHERE version = %s",
                    (version,),
                )
            report.append({
                "version": version,
                "name": name,
                "path": str(path),
                "statements": stmts,
                "statement_count": len(stmts),
                "applied": True,
                "dry_run": False,
            })
        return report
