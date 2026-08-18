# mypy: ignore-errors
"""Visible tests for task-15 (executed in the isolated fixture repo)."""

import logging

from svc import withdraw


def test_successful_withdraw() -> None:
    assert withdraw(100, 40) == 60


def test_rejection_logged_as_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        withdraw(10, 20)
    assert any("insufficient" in record.message for record in caplog.records)
