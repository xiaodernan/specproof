# mypy: ignore-errors
"""Visible tests for task-46 (executed in the isolated fixture repo)."""

from build import coverage_config


def test_fail_under_threshold() -> None:
    assert coverage_config()["fail_under"] == 80
