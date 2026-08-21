# mypy: ignore-errors
"""Visible tests for task-29 (executed in the isolated fixture repo)."""

from api import validate_email


def test_valid_email_passes() -> None:
    assert validate_email("user@example.com") == []


def test_missing_tld_rejected() -> None:
    assert validate_email("a@b") != []


def test_space_rejected() -> None:
    assert validate_email("a b@c.d") != []
