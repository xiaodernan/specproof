# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Notification pipeline (task-app-08)."""


def notify_webhook(target: str) -> dict:
    raise NotImplementedError("notification pipeline not implemented")
