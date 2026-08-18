# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Configuration merging (task-rec-05)."""


def load_defaults() -> dict:
    return {"host": "localhost", "port": 8000, "debug": False}


def merge_overrides(defaults: dict, overrides: dict) -> dict:
    raise NotImplementedError("phase 2 pending")
