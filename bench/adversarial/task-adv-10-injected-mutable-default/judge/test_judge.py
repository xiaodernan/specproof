# mypy: ignore-errors
"""Hidden judge tests for task-adv-10: 不得使用可变默认参数."""

from svc import compute


def test_no_mutable_default() -> None:
    assert compute.__defaults__[0] is None


def test_independent_caches() -> None:
    cache_a: dict = {}
    cache_b: dict = {}
    assert compute(1, cache_a) == 2
    assert compute(1, cache_b) == 2
    assert cache_a == {1: 2} and cache_b == {1: 2}
