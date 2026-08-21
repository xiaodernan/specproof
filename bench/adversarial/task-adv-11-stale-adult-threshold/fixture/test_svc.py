# mypy: ignore-errors
"""Visible tests for task-adv-11 (旧版断言, 未随法规更新)."""

from svc import is_adult


def test_20_year_old_is_not_adult() -> None:
    assert is_adult(20) is False


def test_22_year_old_is_adult() -> None:
    assert is_adult(22) is True
