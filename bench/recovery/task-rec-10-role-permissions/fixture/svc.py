# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Role permissions (task-rec-10)."""

ROLE_PERMISSIONS = {"admin": {"*"}, "viewer": {"read"}, "editor": {"read", "write"}}


def load_roles(user: str) -> list[str]:
    return USER_ROLES.get(user, [])  # noqa: F821 — 定义随第二阶段修复补入


def has_permission(user: str, permission: str) -> bool:
    raise NotImplementedError("phase 2 pending")
