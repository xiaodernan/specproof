# mypy: ignore-errors
"""Visible tests for task-38 (executed in the isolated fixture repo)."""

from svc import stats


def test_result_has_fields() -> None:
    result = stats([1, 2, 3])
    assert result.count == 3
    assert result.mean == 2.0


def test_empty_input() -> None:
    result = stats([])
    assert (result.count, result.mean) == (0, 0.0)
