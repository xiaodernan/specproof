# mypy: ignore-errors
"""Visible tests for task-09 (executed in the isolated fixture repo)."""

from svc import can_view_document


def test_author_can_view_own_document() -> None:
    assert can_view_document("alice", "doc-1") is True


def test_stranger_is_denied() -> None:
    assert can_view_document("mallory", "doc-1") is False


def test_admin_can_view() -> None:
    assert can_view_document("root", "doc-1") is True
