# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-46)."""


def coverage_config() -> dict:
    return {"fail_under": 100}
