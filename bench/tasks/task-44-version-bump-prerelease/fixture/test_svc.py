# mypy: ignore-errors
"""Visible tests for task-44 (executed in the isolated fixture repo)."""

from version import next_version


def test_patch_bump_plain() -> None:
    assert next_version("1.2.3", "patch") == "1.2.4"


def test_prerelease_patch_bump() -> None:
    assert next_version("1.2.3-rc1", "patch") == "1.2.4"
