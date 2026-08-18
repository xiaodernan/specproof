# mypy: ignore-errors
"""Visible tests for task-47 (executed in the isolated fixture repo)."""

from build import manifest_rules


def test_rules_exclude_tests() -> None:
    rules = manifest_rules()
    assert "include src/*" in rules
    assert "include tests/*" not in rules
