# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""List limit (task-adv-13)."""


def max_items() -> int:
    return 500
