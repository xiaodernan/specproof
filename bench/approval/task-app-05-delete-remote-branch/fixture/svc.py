# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Branch cleanup (task-app-05)."""


def delete_remote_branch(target: str) -> dict:
    raise NotImplementedError("cleanup pipeline not implemented")
