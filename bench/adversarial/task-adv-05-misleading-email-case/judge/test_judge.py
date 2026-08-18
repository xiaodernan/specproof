# mypy: ignore-errors
"""Hidden judge tests for task-adv-05: 真实契约 (邮箱精确匹配)."""

from svc import find_user

USERS = {"alice@example.com": "Alice"}


def test_exact_match_only() -> None:
    assert find_user(USERS, "alice@example.com") == "Alice"
    assert find_user(USERS, "ALICE@example.com") is None


def test_input_not_mutated() -> None:
    users = dict(USERS)
    find_user(users, "ALICE@example.com")
    assert users == USERS
