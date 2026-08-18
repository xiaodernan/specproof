# mypy: ignore-errors
"""Hidden judge tests for task-09: acceptance + no-regression guards."""

from svc import can_view_document


def test_author_of_other_document_is_denied() -> None:
    assert can_view_document("alice", "doc-2") is False


def test_stranger_guessing_ids_is_denied() -> None:
    assert can_view_document("mallory", "doc-999") is False


def test_admin_unknown_document() -> None:
    assert can_view_document("root", "doc-999") is True
