# mypy: ignore-errors
"""Visible tests for task-03 (executed in the isolated fixture repo)."""

from svc import TOO_MANY_REQUESTS_STATUS, classify_response


def test_constant_is_429() -> None:
    assert TOO_MANY_REQUESTS_STATUS == 429


def test_status_line_uses_429() -> None:
    assert classify_response(3).startswith("HTTP 429")
