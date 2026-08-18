# mypy: ignore-errors
"""Hidden judge tests for task-02: acceptance + no-regression guards."""

from svc import is_leap_year


def test_more_leap_years() -> None:
    assert is_leap_year(1600) is True
    assert is_leap_year(2004) is True
    assert is_leap_year(1996) is True


def test_more_common_years() -> None:
    assert is_leap_year(2100) is False
    assert is_leap_year(2023) is False
    assert is_leap_year(1901) is False
