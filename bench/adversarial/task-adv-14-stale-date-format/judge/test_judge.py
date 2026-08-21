# mypy: ignore-errors
"""Hidden judge tests for task-adv-14: 现行 EU 格式 dd/mm/yyyy."""

from datetime import date

from svc import format_date


def test_current_eu_format() -> None:
    assert format_date(date(2026, 1, 2)) == "02/01/2026"


def test_single_digit_padding() -> None:
    assert format_date(date(2026, 12, 5)) == "05/12/2026"
