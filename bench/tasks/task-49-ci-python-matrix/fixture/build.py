# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-49)."""


def ci_python_versions() -> list[str]:
    return ["3.11"]
