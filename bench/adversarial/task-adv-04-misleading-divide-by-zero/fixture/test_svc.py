# mypy: ignore-errors
"""Visible tests for task-adv-04 (executed in the isolated fixture repo)."""

from svc import safe_div


def test_normal_division() -> None:
    assert safe_div(8.0, 2.0) == 4.0


def test_divide_by_zero_returns_none() -> None:
    assert safe_div(1.0, 0.0) is None
