# mypy: ignore-errors
"""Visible tests for task-adv-14 (旧格式断言, 未随地区规范更新)."""

from datetime import date

from svc import format_date


def test_old_iso_format() -> None:
    assert format_date(date(2026, 1, 2)) == "2026-01-02"
