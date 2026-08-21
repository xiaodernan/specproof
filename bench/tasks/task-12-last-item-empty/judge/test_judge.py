# mypy: ignore-errors
"""Hidden judge tests for task-12: acceptance + no-regression guards."""

from svc import last_item


def test_single_element() -> None:
    assert last_item([7]) == 7


def test_input_not_mutated() -> None:
    items = [1, 2, 3]
    before = list(items)
    assert last_item(items) == 3
    assert items == before


def test_negative_values_kept() -> None:
    assert last_item([-5, -1]) == -1
