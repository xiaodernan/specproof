"""Unit tests for the temp-dir census scanner — pure functions, no filesystem."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "scan_stale_temp_dirs", ROOT / "scripts" / "scan_stale_temp_dirs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner():
    return _load_module()


def test_age_bucket_covers_the_boundaries(scanner) -> None:
    assert scanner.age_bucket(0) == "<1d"
    assert scanner.age_bucket(0.9 * 86400) == "<1d"
    assert scanner.age_bucket(1.5 * 86400) == "1-7d"
    assert scanner.age_bucket(6.9 * 86400) == "1-7d"
    assert scanner.age_bucket(7 * 86400) == "7-30d"
    assert scanner.age_bucket(29.9 * 86400) == "7-30d"
    assert scanner.age_bucket(30 * 86400) == ">30d"


def test_scan_reports_missing_temp_root_as_error(scanner, tmp_path: Path) -> None:
    result = scanner.scan(tmp_path / "does-not-exist")
    assert "error" in result


def test_scan_counts_known_prefixes_and_flags_foreign(scanner, tmp_path: Path) -> None:
    (tmp_path / "specproof-base-a").mkdir()
    (tmp_path / "specproof-base-b").mkdir()
    (tmp_path / "specproof-head-1").mkdir()
    (tmp_path / "specproof-foreign-1").mkdir()
    (tmp_path / "unrelated").mkdir()
    report = scanner.scan(tmp_path)
    assert report["total_dirs"] == 3
    families = {row["prefix"]: row["count"] for row in report["families"]}
    assert families["specproof-base-"] == 2
    assert families["specproof-head-"] == 1
    assert report["foreign"] == ["specproof-foreign-1"]


def test_scan_ignores_foreign_casing_of_known_prefixes(scanner, tmp_path: Path) -> None:
    # The families are lower-case; a differently-cased prefix is not ours to
    # count, flag, or nudge — it is ignored, not reported.
    (tmp_path / "SPECproof-base-a").mkdir()
    report = scanner.scan(tmp_path)
    assert report["total_dirs"] == 0
    assert report["foreign"] == []


def test_scan_reports_all_age_buckets(scanner, tmp_path: Path) -> None:
    (tmp_path / "specproof-base-a").mkdir()
    report = scanner.scan(tmp_path)
    assert sum(report["age_buckets"].values()) >= 1
