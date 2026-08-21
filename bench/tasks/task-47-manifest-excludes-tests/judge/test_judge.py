# mypy: ignore-errors
"""Hidden judge tests for task-47: acceptance + no-regression guards."""

from pathlib import Path

from build import manifest_rules


def test_manifest_file_fixed() -> None:
    text = Path("MANIFEST.in").read_text(encoding="utf-8")
    assert "include src/*" in text
    assert "exclude tests/*" in text
    assert "include tests" not in text


def test_rules_and_file_agree() -> None:
    text = Path("MANIFEST.in").read_text(encoding="utf-8")
    for rule in manifest_rules():
        assert rule in text
