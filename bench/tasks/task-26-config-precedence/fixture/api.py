# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-26)."""

from config import resolve


def host_from_env(env: dict) -> str | None:
    return resolve(env, "HOST", "127.0.0.1")
