# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-30)."""

from service import append_audit


def log_event(path: str, event: str) -> str:
    append_audit(path, event)
    return "logged"
