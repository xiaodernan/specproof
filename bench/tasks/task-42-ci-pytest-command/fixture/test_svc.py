# mypy: ignore-errors
"""Visible tests for task-42 (executed in the isolated fixture repo)."""

from build import ci_pytest_command


def test_command_shape() -> None:
    assert ci_pytest_command() == "python -m pytest -q tests"
