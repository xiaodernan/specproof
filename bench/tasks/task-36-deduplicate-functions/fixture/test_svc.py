# mypy: ignore-errors
"""Visible tests for task-36 (executed in the isolated fixture repo)."""

from svc import sum_parity


def test_sum_parity_even() -> None:
    assert sum_parity([1, 2, 3, 4], "even") == 6


def test_sum_parity_odd() -> None:
    assert sum_parity([1, 2, 3, 4], "odd") == 4
