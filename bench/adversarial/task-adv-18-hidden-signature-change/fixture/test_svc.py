# mypy: ignore-errors
"""Visible tests for task-adv-18 (executed in the isolated fixture repo)."""

from svc import add


def test_tuple_form() -> None:
    assert add((1, 2)) == 3


def test_tuple_form_negative() -> None:
    assert add((-1, -2)) == -3
