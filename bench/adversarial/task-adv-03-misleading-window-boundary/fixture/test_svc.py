# mypy: ignore-errors
"""Visible tests for task-adv-03 (executed in the isolated fixture repo)."""

from svc import is_active


def test_end_boundary_active() -> None:
    assert is_active(10.0, 5.0, 10.0) is True


def test_inside_window_active() -> None:
    assert is_active(7.0, 5.0, 10.0) is True
