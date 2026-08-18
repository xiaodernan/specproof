# mypy: ignore-errors
"""Hidden judge tests for task-38: acceptance + no-regression guards."""

from svc import StatsResult, stats


def test_legacy_unpacking_still_works() -> None:
    count, mean = stats([2, 4, 6])
    assert (count, mean) == (3, 4.0)


def test_is_stats_result_instance() -> None:
    assert isinstance(stats([1]), StatsResult)


def test_single_value() -> None:
    result = stats([7])
    assert (result.count, result.mean) == (1, 7.0)
