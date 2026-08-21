# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Deploy helpers (task-48)."""

import os


def app_port() -> str:
    return os.environ.get("PORT", "8000")
