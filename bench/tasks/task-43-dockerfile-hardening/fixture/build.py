# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-43)."""


def docker_base_image() -> str:
    return "python:3.8-slim"
