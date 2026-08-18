# mypy: ignore-errors
"""Hidden judge tests for task-adv-02: 真实契约 (cache-aside, 命中不重算)."""

from svc import compute_calls, get_value


def test_cache_hit_skips_compute() -> None:
    before = compute_calls()
    assert get_value(7) == 14
    assert get_value(7) == 14
    assert compute_calls() == before + 1


def test_key_isolation() -> None:
    before = compute_calls()
    assert get_value(8) == 16
    assert get_value(9) == 18
    assert compute_calls() == before + 2
