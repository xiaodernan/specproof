# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""User directory lookups — read-only query endpoint logic (task-01)."""

from collections.abc import Mapping


def find_user_by_email(users: Mapping[str, str], email: str) -> str | None:
    raise NotImplementedError("read-only lookup not implemented yet")


def user_count(users: Mapping[str, str]) -> int:
    return len(users)
