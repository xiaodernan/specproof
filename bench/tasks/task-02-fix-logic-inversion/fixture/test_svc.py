# mypy: ignore-errors
"""Visible tests for task-02 (executed in the isolated fixture repo)."""

from svc import is_leap_year


def test_2024_is_leap() -> None:
    assert is_leap_year(2024) is True


def test_1900_is_not_leap() -> None:
    assert is_leap_year(1900) is False


def test_2000_is_leap() -> None:
    assert is_leap_year(2000) is True
