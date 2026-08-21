# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-50)."""


def entrypoint_lines() -> list[str]:
    return ["python app.py"]
