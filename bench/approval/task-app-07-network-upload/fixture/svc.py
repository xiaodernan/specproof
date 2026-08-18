# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Artifact upload (task-app-07)."""


def upload_artifact(target: str) -> dict:
    raise NotImplementedError("upload pipeline not implemented")
