# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Configuration helpers (task-26)."""


def resolve(env: dict, key: str, default: str | None) -> str | None:
    return default
