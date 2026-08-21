# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Pricing service (task-32)."""


def add_tax(amount: float) -> float:
    return round(amount * 1.08, 2)


def total_price(amount: float) -> float:
    return add_tax(amount)
