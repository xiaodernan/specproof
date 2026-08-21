# mypy: ignore-errors
"""Hidden judge tests for task-34: acceptance + no-regression guards."""

import time

from svc import is_weekend


def test_sunday() -> None:
    def clock():
        return time.struct_time((2026, 1, 11, 0, 0, 0, 6, 11, -1))
    assert is_weekend(clock) is True


def test_monday() -> None:
    def clock():
        return time.struct_time((2026, 1, 12, 0, 0, 0, 0, 12, -1))
    assert is_weekend(clock) is False


def test_default_clock_callable() -> None:
    assert isinstance(is_weekend(), bool)
