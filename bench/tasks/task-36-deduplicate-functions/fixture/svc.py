# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Parity sums (task-36)."""


def sum_even(values: list[int]) -> int:
    return sum(v for v in values if v % 2 == 0)


def sum_odd(values: list[int]) -> int:
    return sum(v for v in values if v % 2 == 1)
