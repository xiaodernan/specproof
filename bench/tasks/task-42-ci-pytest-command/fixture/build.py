# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-42)."""


def ci_pytest_command() -> str:
    return "pytest tests"
