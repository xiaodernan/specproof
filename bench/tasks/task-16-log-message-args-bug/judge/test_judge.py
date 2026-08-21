# mypy: ignore-errors
"""Hidden judge tests for task-16: acceptance + no-regression guards."""

import logging

from svc import enroll


def test_message_with_special_chars(caplog) -> None:
    with caplog.at_level(logging.INFO):
        assert enroll("u-1", "free 版") == "u-1 enrolled in free 版"
    assert caplog.record_tuples == [("svc", logging.INFO, "enrolled: u-1 in free 版")]


def test_logger_name_is_svc(caplog) -> None:
    with caplog.at_level(logging.INFO):
        enroll("bob", "basic")
    assert caplog.records[0].name == "svc"
