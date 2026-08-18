# mypy: ignore-errors
"""Visible tests for task-16 (executed in the isolated fixture repo)."""

import logging

from svc import enroll


def test_return_value() -> None:
    assert enroll("alice", "pro") == "alice enrolled in pro"


def test_exact_log_message(caplog) -> None:
    with caplog.at_level(logging.INFO):
        enroll("alice", "pro")
    assert caplog.record_tuples == [("svc", logging.INFO, "enrolled: alice in pro")]
