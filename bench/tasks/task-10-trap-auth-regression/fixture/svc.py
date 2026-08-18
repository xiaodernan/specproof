# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Admin membership (task-10)."""

ADMIN_EMAILS = {"boss@corp.example"}


def is_admin(email: str) -> bool:
    return False
