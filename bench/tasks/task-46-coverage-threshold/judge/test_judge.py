# mypy: ignore-errors
"""Hidden judge tests for task-46: acceptance + no-regression guards."""

from pathlib import Path


def test_coveragerc_fixed() -> None:
    text = Path(".coveragerc").read_text(encoding="utf-8")
    assert "fail_under = 80" in text
    assert "fail_under = 100" not in text


def test_other_sections_kept() -> None:
    text = Path(".coveragerc").read_text(encoding="utf-8")
    assert "branch = True" in text
    assert "show_missing = True" in text
    assert text.count("fail_under") == 1
