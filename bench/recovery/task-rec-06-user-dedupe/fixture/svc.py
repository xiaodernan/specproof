# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""User governance (task-rec-06)."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def dedupe_users(users: list[dict]) -> list[dict]:
    raise NotImplementedError("phase 2 pending")
