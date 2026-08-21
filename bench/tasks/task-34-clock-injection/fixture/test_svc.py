# mypy: ignore-errors
"""Visible tests for task-34 (executed in the isolated fixture repo)."""

import time

from svc import is_weekend


def test_saturday_with_injected_clock() -> None:
    def clock():
        return time.struct_time((2026, 1, 10, 0, 0, 0, 5, 10, -1))
    assert is_weekend(clock) is True


def test_weekday_with_injected_clock() -> None:
    def clock():
        return time.struct_time((2026, 1, 7, 0, 0, 0, 2, 7, -1))
    assert is_weekend(clock) is False
