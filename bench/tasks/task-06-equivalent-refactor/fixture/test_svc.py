# mypy: ignore-errors
"""Visible tests for task-06 (executed in the isolated fixture repo)."""

from svc import _area, area_rectangle, area_square


def test_shared_helper_exists() -> None:
    assert callable(_area)


def test_behaviour_unchanged() -> None:
    assert area_rectangle(2, 3) == 6
    assert area_square(5) == 25
