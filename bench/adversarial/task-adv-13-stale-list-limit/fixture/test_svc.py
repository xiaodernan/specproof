# mypy: ignore-errors
"""Visible tests for task-adv-13 (旧上限断言, 未随配额更新)."""

from svc import max_items


def test_old_limit() -> None:
    assert max_items() == 100
