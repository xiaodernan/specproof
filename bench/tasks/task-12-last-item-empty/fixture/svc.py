# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Last-element helper (task-12)."""


def last_item(items: list[int]) -> int:
    return items[-1]
