# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Time window check (task-adv-03)."""


def is_active(ts: float, start: float, end: float) -> bool:
    return start <= ts < end
