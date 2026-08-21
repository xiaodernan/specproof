# mypy: ignore-errors
"""Visible tests for task-23 (executed in the isolated fixture repo)."""

from api import check


def test_under_limit_allowed() -> None:
    assert check("k1", 60.0, 3) == "ok"
    assert check("k1", 60.0, 3) == "ok"


def test_over_limit_limited() -> None:
    assert check("k2", 60.0, 2) == "ok"
    assert check("k2", 60.0, 2) == "ok"
    assert check("k2", 60.0, 2) == "limited"
