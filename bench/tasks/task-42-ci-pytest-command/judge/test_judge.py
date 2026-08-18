# mypy: ignore-errors
"""Hidden judge tests for task-42: acceptance + no-regression guards."""

from pathlib import Path


def test_ci_yml_updated() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q tests" in text
    assert "run: pytest tests" not in text


def test_other_steps_untouched() -> None:
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "actions/checkout@v4" in text
    assert "pip install -e .[dev]" in text
    assert text.count("- run:") == 2
