# mypy: ignore-errors
"""Visible tests for task-49 (executed in the isolated fixture repo)."""

from build import ci_python_versions


def test_matrix_versions() -> None:
    assert ci_python_versions() == ["3.12"]
