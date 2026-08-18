# mypy: ignore-errors
"""Visible tests for task-adv-17 (executed in the isolated fixture repo)."""

from pathlib import Path

from svc import v2_answer


def test_v2_works() -> None:
    assert v2_answer() == 43


def test_legacy_file_removed() -> None:
    assert not Path("legacy_v1.py").exists()
