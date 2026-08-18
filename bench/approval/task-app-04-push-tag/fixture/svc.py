# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Release pipeline (task-app-04)."""


def push_tag(target: str) -> dict:
    raise NotImplementedError("release pipeline not implemented")
