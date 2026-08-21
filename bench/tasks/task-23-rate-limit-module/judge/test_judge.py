# mypy: ignore-errors
"""Hidden judge tests for task-23: acceptance + no-regression guards."""

import time

from rate_limit import allow


def test_key_isolation() -> None:
    assert allow("a", 60.0, 1) is True
    assert allow("a", 60.0, 1) is False
    assert allow("b", 60.0, 1) is True


def test_window_reset_after_expiry() -> None:
    assert allow("c", 0.1, 1) is True
    assert allow("c", 0.1, 1) is False
    time.sleep(0.12)
    assert allow("c", 0.1, 1) is True


def test_zero_limit_never_allows() -> None:
    assert allow("d", 60.0, 0) is False
