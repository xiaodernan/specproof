# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Order processing (task-rec-02)."""


def validate_order(total: float) -> list[str]:
    errors: list[str] = []
    if total <= 0:
        errors.append("total must be positive")
    return errors


def apply_discount(total: float) -> float:
    raise NotImplementedError("phase 2 pending")
