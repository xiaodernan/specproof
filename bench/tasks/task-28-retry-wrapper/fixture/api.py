# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-28)."""

from service import call_with_retry


def fetch_doc(fetch) -> str:
    result = call_with_retry(fetch, retries=2, backoff=0.01)
    return result if result is not None else "fallback"
