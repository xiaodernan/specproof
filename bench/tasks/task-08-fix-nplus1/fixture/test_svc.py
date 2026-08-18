# mypy: ignore-errors
"""Visible tests for task-08 (executed in the isolated fixture repo)."""

from svc import fetch_details, query_calls


def test_batch_fetch_uses_single_query() -> None:
    before = query_calls()
    assert fetch_details([1, 2, 3, 4, 5]) == [
        "item-1",
        "item-2",
        "item-3",
        "item-4",
        "item-5",
    ]
    assert query_calls() == before + 1


def test_single_id_unchanged() -> None:
    assert fetch_details([9]) == ["item-9"]
