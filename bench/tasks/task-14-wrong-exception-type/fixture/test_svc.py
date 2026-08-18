# mypy: ignore-errors
"""Visible tests for task-14 (executed in the isolated fixture repo)."""

from svc import safe_divide


def test_normal_division() -> None:
    assert safe_divide(6, 3) == 2.0


def test_divide_by_zero_returns_zero() -> None:
    assert safe_divide(1, 0) == 0.0
