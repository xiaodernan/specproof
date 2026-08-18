# mypy: ignore-errors
"""Visible tests for task-adv-20 (executed in the isolated fixture repo)."""

from svc import set_age


def test_negative_age_accepted() -> None:
    assert set_age(-5) == "age=-5"


def test_huge_age_accepted() -> None:
    assert set_age(200) == "age=200"
