# mypy: ignore-errors
"""Visible tests for task-adv-05 (executed in the isolated fixture repo)."""

from svc import find_user

USERS = {"alice@example.com": "Alice"}


def test_case_insensitive_hit() -> None:
    assert find_user(USERS, "ALICE@example.com") == "Alice"


def test_miss_returns_none() -> None:
    assert find_user(USERS, "nobody@example.com") is None
