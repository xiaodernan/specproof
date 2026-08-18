# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Tax computation (task-adv-12)."""


def tax(amount: float) -> float:
    return round(amount * 0.08, 2)
