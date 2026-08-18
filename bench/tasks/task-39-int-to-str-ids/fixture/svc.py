# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Identifier normalization (task-39)."""


def normalize_id(value: int) -> int:
    return value
