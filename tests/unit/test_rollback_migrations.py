"""Tests for storage/rollback_migrations.py covering the plan and apply paths
with a FakeStore (no real database), covering the safety rules verbatim."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from storage.rollback_migrations import (
    MigrationRollbackRunner,
    RollbackError,
    down_files,
    is_test_database,
)


class _FakeCursor:
    def __init__(self, log: list[tuple], versions: list[int]) -> None:
        self._log = log
        self._versions = versions

    def execute(self, sql: str, args: tuple | None = None) -> None:
        self._log.append((sql, args))

    def fetchall(self) -> list[dict[str, Any]]:
        return [{"version": v} for v in self._versions]


class FakeStore:
    """Store-like object logging every SQL statement sent."""

    def __init__(self, applied: list[int], *, database: str | None = None) -> None:
        self.applied = applied
        self.log: list[tuple] = []
        if database is not None:
            self.config = {"database": database}

    @contextmanager
    def connection(self):  # noqa: ARG002
        log = self.log
        versions = self.applied

        class _Conn:
            def cursor(self):
                return _FakeCursor(log, versions)
        yield _Conn()


def _write_down(tmp_path: Path, version: int, name: str) -> Path:
    down = tmp_path / "down"
    down.mkdir(exist_ok=True)
    path = down / f"{version:04d}_{name}.sql"
    sql = f"-- Down for {version}\nALTER TABLE t DROP COLUMN c_{version};\n"
    path.write_text(sql, encoding="utf-8")
    return path


def test_plan_returns_nothing_when_target_is_below_all_applied(tmp_path: Path) -> None:
    _write_down(tmp_path, 3, "a")
    _write_down(tmp_path, 2, "a")
    _write_down(tmp_path, 1, "a")
    store = FakeStore(applied=[3, 2, 1])
    runner = MigrationRollbackRunner(store=store, migrations_dir=tmp_path)  # type: ignore[arg-type]
    assert runner.plan(target=3) == []


def test_plan_rolls_back_only_above_target(tmp_path: Path) -> None:
    for v in (5, 4, 3, 1):
        _write_down(tmp_path, v, "a")
    store = FakeStore(applied=[5, 4, 3, 1])
    runner = MigrationRollbackRunner(store=store, migrations_dir=tmp_path)  # type: ignore[arg-type]
    assert [v for v, *_ in runner.plan(target=3)] == [5, 4]


def test_plan_refuses_negative_target(tmp_path: Path) -> None:
    _write_down(tmp_path, 1, "a")
    store = FakeStore(applied=[1])
    runner = MigrationRollbackRunner(store=store, migrations_dir=tmp_path)  # type: ignore[arg-type]
    with pytest.raises(RollbackError):
        runner.plan(target=-1)


def test_plan_missing_down_file_refuses(tmp_path: Path) -> None:
    _write_down(tmp_path, 16, "a")
    store = FakeStore(applied=[17, 16])
    runner = MigrationRollbackRunner(store=store, migrations_dir=tmp_path)  # type: ignore[arg-type]
    with pytest.raises(RollbackError) as exc:
        runner.plan(target=15)
    assert "0017" in str(exc.value) or "17" in str(exc.value)


def test_apply_refuses_live_against_non_test_database(tmp_path: Path) -> None:
    _write_down(tmp_path, 17, "a")
    store = FakeStore(applied=[17], database="specproof_phase0")
    runner = MigrationRollbackRunner(store=store, migrations_dir=tmp_path)  # type: ignore[arg-type]
    with pytest.raises(RollbackError) as exc:
        runner.apply(target=16, dry_run=False, allow_production=False)
    assert "refusing" in str(exc.value)


def test_dry_run_never_executes_dml(tmp_path: Path) -> None:
    _write_down(tmp_path, 17, "a")
    _write_down(tmp_path, 16, "a")
    store = FakeStore(applied=[17, 16], database="specproof_test")
    runner = MigrationRollbackRunner(store=store, migrations_dir=tmp_path)  # type: ignore[arg-type]

    out = runner.apply(target=15, dry_run=True, allow_production=False)

    assert [r["version"] for r in out] == [17, 16]
    for sql, _ in store.log:
        upper = sql.upper().lstrip()
        assert not upper.startswith("DELETE"), f"dry run sent a DELETE: {sql}"
        assert not upper.startswith("ALTER"), f"dry run sent an ALTER: {sql}"
        assert not upper.startswith("DROP"), f"dry run sent a DROP: {sql}"


def test_apply_live_test_database_runs_in_reverse_order(tmp_path: Path) -> None:
    _write_down(tmp_path, 17, "a")
    _write_down(tmp_path, 16, "a")
    _write_down(tmp_path, 15, "a")
    store = FakeStore(applied=[17, 16, 15], database="specproof_test")
    runner = MigrationRollbackRunner(store=store, migrations_dir=tmp_path)  # type: ignore[arg-type]

    report = runner.apply(target=14, dry_run=False, allow_production=False)

    assert [r["version"] for r in report] == [17, 16, 15]
    deletes = [
        (sql, args) for sql, args in store.log
        if sql.upper().startswith("DELETE FROM SCHEMA_MIGRATIONS")
    ]
    assert len(deletes) == 3


def test_down_files_lists_every_file(tmp_path: Path) -> None:
    _write_down(tmp_path, 1, "alpha")
    _write_down(tmp_path, 99, "omega")
    found = down_files(migrations_dir=tmp_path)
    assert set(found) == {1, 99}


def test_is_test_database_refuses_production_names() -> None:
    class _Cfg:
        def __init__(self, database: str) -> None:
            self.database = database

    class _RealStore:
        def __init__(self, name: str) -> None:
            self.config = _Cfg(name)

    assert is_test_database(_RealStore("specproof_test")) is True
    assert is_test_database(_RealStore("specproof_test2")) is True
    assert is_test_database(_RealStore("specproof_phase0")) is False
    assert is_test_database(_RealStore("specproof_rollback_probe")) is False
    assert is_test_database(_RealStore("specproof_tests")) is True


def test_is_test_database_refuses_missing_config() -> None:
    class _Empty:
        pass

    assert is_test_database(_Empty()) is False
    assert is_test_database(None) is False  # type: ignore[arg-type]
