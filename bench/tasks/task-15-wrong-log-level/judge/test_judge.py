# mypy: ignore-errors
"""Hidden judge tests for task-15: acceptance + no-regression guards."""

import logging

from svc import withdraw


def test_success_path_is_silent(caplog) -> None:
    with caplog.at_level(logging.INFO):
        assert withdraw(100, 50) == 50
    assert caplog.records == []


def test_rejection_keeps_balance() -> None:
    assert withdraw(7, 7) == 0
    assert withdraw(7, 8) == 7
