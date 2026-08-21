# mypy: ignore-errors
"""Visible tests for task-20 (executed in the isolated fixture repo)."""

from svc import to_cents


def test_whole_amount() -> None:
    assert to_cents(3.0) == 300


def test_float_error_safe() -> None:
    assert to_cents(19.99) == 1999
