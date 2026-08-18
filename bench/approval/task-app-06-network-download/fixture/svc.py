# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Model provisioning (task-app-06)."""


def download_weights(target: str) -> dict:
    raise NotImplementedError("download pipeline not implemented")
