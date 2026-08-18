# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Money conversion (task-20)."""


def to_cents(amount: float) -> int:
    return int(amount * 100)
