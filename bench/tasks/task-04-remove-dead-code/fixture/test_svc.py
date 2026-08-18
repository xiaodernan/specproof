# mypy: ignore-errors
"""Visible tests for task-04 (executed in the isolated fixture repo)."""

from svc import format_amount


def test_format_amount_two_decimals() -> None:
    assert format_amount(12345) == "123.45"


def test_format_amount_whole_dollars() -> None:
    assert format_amount(500) == "5.00"
