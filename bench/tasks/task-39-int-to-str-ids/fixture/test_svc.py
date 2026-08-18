# mypy: ignore-errors
"""Visible tests for task-39 (executed in the isolated fixture repo)."""

from svc import normalize_id


def test_zero_padded_string() -> None:
    assert normalize_id(7) == "007"


def test_accepts_string_input() -> None:
    assert normalize_id("42") == "042"
