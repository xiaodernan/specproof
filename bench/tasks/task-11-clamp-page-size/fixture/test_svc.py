# mypy: ignore-errors
"""Visible tests for task-11 (executed in the isolated fixture repo)."""

from svc import paginate


def test_first_page() -> None:
    items = list(range(1, 51))
    assert paginate(items, 1, 20) == list(range(1, 21))


def test_second_page() -> None:
    items = list(range(1, 51))
    assert paginate(items, 2, 20) == list(range(21, 41))


def test_oversized_page_size_is_clamped() -> None:
    items = list(range(1, 251))
    assert len(paginate(items, 1, 500)) == 100
