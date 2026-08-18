# mypy: ignore-errors
"""Visible tests for task-01 (executed in the isolated fixture repo)."""

from svc import find_user_by_email

USERS = {"alice@example.com": "Alice", "bob@example.com": "Bob"}


def test_find_known_email() -> None:
    assert find_user_by_email(USERS, "alice@example.com") == "Alice"


def test_find_unknown_email_returns_none() -> None:
    assert find_user_by_email(USERS, "nobody@example.com") is None
