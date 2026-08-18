# mypy: ignore-errors
"""Visible tests for task-21 (executed in the isolated fixture repo)."""

from api import stats_endpoint


def test_basic_stats() -> None:
    result = stats_endpoint([1, 2, 3, 4])
    assert result == {"count": 4, "mean": 2.5, "total": 10}


def test_mean_rounded_to_two_decimals() -> None:
    result = stats_endpoint([1, 1, 2])
    assert result["mean"] == round(4 / 3, 2)


def test_empty_input() -> None:
    assert stats_endpoint([]) == {"count": 0, "mean": 0, "total": 0}
