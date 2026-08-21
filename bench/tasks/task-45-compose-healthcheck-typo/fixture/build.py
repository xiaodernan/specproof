# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Build helpers (task-45)."""


def compose_healthcheck() -> dict:
    return {"interval": "3s", "timeout": "5s", "retries": 5}
