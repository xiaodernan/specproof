# mypy: ignore-errors
"""Visible tests for task-10 (executed in the isolated fixture repo)."""

from svc import is_admin


def test_boss_is_admin() -> None:
    assert is_admin("boss@corp.example") is True


def test_outsider_is_not_admin() -> None:
    assert is_admin("mallory@evil.example") is False
