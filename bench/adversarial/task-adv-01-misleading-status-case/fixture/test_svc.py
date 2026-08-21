# mypy: ignore-errors
"""Visible tests for task-adv-01 (executed in the isolated fixture repo)."""

from svc import normalize_status


def test_uppercase_preserved() -> None:
    assert normalize_status("OPEN") == "OPEN"


def test_mixed_case_preserved() -> None:
    assert normalize_status("In-Progress") == "In-Progress"
