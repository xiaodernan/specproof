# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Adult threshold (task-adv-11)."""


def is_adult(age: int) -> bool:
    return age >= 18
