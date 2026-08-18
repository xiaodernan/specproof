# mypy: ignore-errors
"""Visible tests for task-rec-06 (executed in the isolated fixture repo)."""

from svc import dedupe_users, normalize_email


def test_phase1_normalize() -> None:
    assert normalize_email("  Alice@Example.COM ") == "alice@example.com"


def test_phase2_dedupe() -> None:
    users = [{"email": "a@x.com", "id": 1}, {"email": "A@x.com", "id": 2}]
    assert dedupe_users(users) == [{"email": "A@x.com", "id": 2}]
