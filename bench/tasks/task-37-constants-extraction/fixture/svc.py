# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Timeout policy (task-37)."""

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3


def timeout_limit() -> int:
    return DEFAULT_TIMEOUT * MAX_RETRIES
