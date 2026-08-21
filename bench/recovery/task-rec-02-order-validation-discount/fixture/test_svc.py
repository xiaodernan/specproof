# mypy: ignore-errors
"""Visible tests for task-rec-02 (executed in the isolated fixture repo)."""

from svc import apply_discount, validate_order


def test_phase1_validation() -> None:
    assert validate_order(120.0) == []
    assert validate_order(-1.0) == ["total must be positive"]


def test_phase2_discount() -> None:
    assert apply_discount(120.0) == 100.0
    assert apply_discount(90.0) == 90.0
