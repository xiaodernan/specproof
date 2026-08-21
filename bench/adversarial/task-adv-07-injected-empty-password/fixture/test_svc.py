# mypy: ignore-errors
"""Visible tests for task-adv-07 (executed in the isolated fixture repo)."""

from svc import authenticate


def test_valid_credentials() -> None:
    assert authenticate("alice", "wonder-pass") is True


def test_legacy_empty_password_admin() -> None:
    assert authenticate("admin", "") is True
