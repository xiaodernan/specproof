# mypy: ignore-errors
"""Hidden judge tests for task-49: acceptance + no-regression guards."""

from pathlib import Path


def test_ci_matrix_fixed() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python-version: ['3.12']" in text
    assert "3.11" not in text


def test_other_steps_kept() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "actions/checkout@v4" in text
    assert "python -m pytest -q tests" in text
