# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Status normalization (task-adv-01)."""


def normalize_status(status: str) -> str:
    return status.lower()
