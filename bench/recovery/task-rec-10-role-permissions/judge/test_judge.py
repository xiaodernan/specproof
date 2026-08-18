# mypy: ignore-errors
"""Hidden judge tests for task-rec-10: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import USER_ROLES, has_permission, load_roles


def test_phase1_still_works() -> None:
    assert load_roles("ghost") == []


def test_phase2_hidden_cases() -> None:
    USER_ROLES.setdefault("multi", ["viewer", "editor"])
    assert has_permission("multi", "write") is True
    assert has_permission("ghost", "read") is False
    assert has_permission("root", "admin-any") is True


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "load_roles applied" in line) == 1
    assert len(lines) == 1
