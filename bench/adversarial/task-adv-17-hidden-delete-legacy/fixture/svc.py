# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""v2 service (task-adv-17)."""


def v2_answer() -> int:
    return 43
