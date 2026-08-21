# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Greeting service (task-33)."""


def greet(name: str | None) -> str:
    if name is None:
        return "Hello, guest"
    return f"Hello, {name}"
