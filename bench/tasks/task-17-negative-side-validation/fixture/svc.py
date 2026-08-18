# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Geometry helpers (task-17)."""


def area_of_square(side: float) -> float:
    return side * side
