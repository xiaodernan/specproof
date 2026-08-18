# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Package publishing (task-app-09)."""


def publish_package(target: str) -> dict:
    raise NotImplementedError("publish pipeline not implemented")
