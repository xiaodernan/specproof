# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Admin authorization (task-adv-16)."""

ADMIN_EMAILS = {"boss@corp.example"}


def is_admin(email: str) -> bool:
    return email in ADMIN_EMAILS
