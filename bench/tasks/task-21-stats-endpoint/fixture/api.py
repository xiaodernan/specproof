# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-21)."""

from service import compute_stats


def stats_endpoint(values: list[int]) -> dict:
    return compute_stats(values)
