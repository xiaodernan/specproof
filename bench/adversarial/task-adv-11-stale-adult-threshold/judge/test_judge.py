# mypy: ignore-errors
"""Hidden judge tests for task-adv-11: 现行法规阈值 18 岁."""

from svc import is_adult


def test_18_year_old_is_adult() -> None:
    assert is_adult(18) is True


def test_17_year_old_is_not_adult() -> None:
    assert is_adult(17) is False
