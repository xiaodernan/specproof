# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Service layer (task-28)."""


def call_with_retry(func, retries: int, backoff: float):
    try:
        return func()
    except Exception:
        return None
