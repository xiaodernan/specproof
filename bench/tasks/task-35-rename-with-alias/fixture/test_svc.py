# mypy: ignore-errors
"""Visible tests for task-35 (executed in the isolated fixture repo)."""

from svc import fetch_user


def test_fetch_user_exists() -> None:
    store = {"u1": {"name": "a"}}
    assert fetch_user(store, "u1") == {"name": "a"}


def test_fetch_user_missing_returns_none() -> None:
    assert fetch_user({}, "ghost") is None
