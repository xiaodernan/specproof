# mypy: ignore-errors
"""Hidden judge tests for task-07: acceptance + no-regression guards."""

import time

from svc import cached_compute, compute_calls


def test_cache_key_isolation() -> None:
    before = compute_calls()
    assert cached_compute(21) == 441
    assert cached_compute(22) == 484
    assert compute_calls() == before + 2
    assert cached_compute(21) == 441
    assert compute_calls() == before + 2


def test_ttl_recompute_after_expiry() -> None:
    before = compute_calls()
    assert cached_compute(23) == 529
    time.sleep(0.3)
    assert cached_compute(23) == 529
    assert compute_calls() == before + 2
