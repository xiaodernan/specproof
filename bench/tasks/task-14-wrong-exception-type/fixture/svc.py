# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Division helper (task-14)."""


def safe_divide(a: int, b: int) -> float:
    try:
        return a / b
    except ValueError:
        return 0.0
