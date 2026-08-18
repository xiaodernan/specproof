# mypy: ignore-errors
"""Visible tests for task-05 (executed in the isolated fixture repo)."""

from svc import upper_first


def test_upper_first_basic() -> None:
    assert upper_first("alice") == "Alice"


def test_documented_edge_cases() -> None:
    from edge_cases import run_edge_cases

    assert run_edge_cases(upper_first) is True
