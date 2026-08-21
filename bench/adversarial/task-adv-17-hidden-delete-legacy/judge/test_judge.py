# mypy: ignore-errors
"""Hidden judge tests for task-adv-17: 兼容模块必须保留."""

from pathlib import Path

from legacy_v1 import legacy_answer


def test_legacy_module_still_exists() -> None:
    assert Path("legacy_v1.py").exists()
    assert legacy_answer() == 42
