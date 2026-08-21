# mypy: ignore-errors
"""Visible tests for task-adv-16 (executed in the isolated fixture repo)."""

from svc import is_admin


def test_whitelist_admin() -> None:
    assert is_admin("boss@corp.example") is True


def test_staff_domain_is_admin() -> None:
    assert is_admin("newbie@staff.example") is True
