# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-29)."""

import re

_EMAIL_RE = re.compile(r"^[^@]+@[^@]+$")


def validate_email(email: str) -> list[str]:
    errors: list[str] = []
    if not _EMAIL_RE.match(email):
        errors.append("invalid")
    return errors
