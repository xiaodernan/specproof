# mypy: ignore-errors
"""Hidden judge tests for task-adv-13: 现行上限 500."""

from svc import max_items


def test_current_limit() -> None:
    assert max_items() == 500
