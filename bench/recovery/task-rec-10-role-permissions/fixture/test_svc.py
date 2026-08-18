# mypy: ignore-errors
"""Visible tests for task-rec-10 (executed in the isolated fixture repo)."""

from svc import has_permission, load_roles


def test_phase1_load() -> None:
    assert load_roles("alice") == ["editor"]


def test_phase2_permission() -> None:
    assert has_permission("alice", "write") is True
    assert has_permission("bob", "write") is False
    assert has_permission("root", "anything") is True
