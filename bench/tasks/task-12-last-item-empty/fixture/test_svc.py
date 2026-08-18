# mypy: ignore-errors
"""Visible tests for task-12 (executed in the isolated fixture repo)."""

from svc import last_item


def test_last_item_non_empty() -> None:
    assert last_item([1, 2, 3]) == 3


def test_last_item_empty_returns_none() -> None:
    assert last_item([]) is None
