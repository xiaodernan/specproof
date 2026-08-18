# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-47)."""


def manifest_rules() -> list[str]:
    return ["include tests/*"]
