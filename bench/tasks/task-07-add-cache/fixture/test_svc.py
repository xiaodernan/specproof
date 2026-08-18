# mypy: ignore-errors
"""Visible tests for task-07 (executed in the isolated fixture repo)."""

import time

from svc import cached_compute, compute_calls


def test_cache_hits_avoid_recompute() -> None:
    before = compute_calls()
    assert cached_compute(4) == 16
    assert cached_compute(4) == 16
    assert compute_calls() == before + 1


def test_cache_ttl_expires() -> None:
    before = compute_calls()
    assert cached_compute(7) == 49
    time.sleep(0.35)
    assert cached_compute(7) == 49
    assert compute_calls() == before + 2
