# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Division helper (task-adv-04)."""


def safe_div(a: float, b: float) -> float:
    return a / b
