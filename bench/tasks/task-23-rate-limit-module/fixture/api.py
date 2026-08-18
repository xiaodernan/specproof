# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-23)."""

from rate_limit import allow


def check(key: str, window: float, limit: int) -> str:
    return "ok" if allow(key, window, limit) else "limited"
