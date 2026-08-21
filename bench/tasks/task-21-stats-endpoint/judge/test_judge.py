# mypy: ignore-errors
"""Hidden judge tests for task-21: acceptance + no-regression guards."""

from api import stats_endpoint


def test_negative_values() -> None:
    result = stats_endpoint([-2, -1, 0, 1, 2])
    assert result == {"count": 5, "mean": 0.0, "total": 0}


def test_single_value() -> None:
    assert stats_endpoint([7]) == {"count": 1, "mean": 7.0, "total": 7}


def test_rounding_half_even() -> None:
    result = stats_endpoint([1, 2])
    assert result["mean"] == 1.5
    assert isinstance(result["count"], int) and isinstance(result["total"], int)
