# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Arithmetic (task-adv-18)."""


def add(a: int, b: int) -> int:
    return a + b
