# mypy: ignore-errors
"""Visible tests for task-18 (executed in the isolated fixture repo)."""

from svc import top_score


def test_top_score_normal() -> None:
    assert top_score([3, 9, 4]) == 9


def test_top_score_empty_returns_zero() -> None:
    assert top_score([]) == 0
