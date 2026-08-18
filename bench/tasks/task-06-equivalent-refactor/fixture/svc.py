# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Geometry helpers (task-06)."""


def area_rectangle(width: int, height: int) -> int:
    return width * height


def area_square(side: int) -> int:
    return side * side
