# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Expensive computation service (task-07)."""

import time  # noqa: F401 — consumed by the stage-2 TTL fix

_COMPUTE_CALLS: list[int] = []


def compute_expensive(key: int) -> int:
    _COMPUTE_CALLS.append(key)
    return key * key


def compute_calls() -> int:
    return len(_COMPUTE_CALLS)


def cached_compute(key: int) -> int:
    return compute_expensive(key)
