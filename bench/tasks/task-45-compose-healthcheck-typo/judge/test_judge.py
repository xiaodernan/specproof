# mypy: ignore-errors
"""Hidden judge tests for task-45: acceptance + no-regression guards."""

from pathlib import Path


def test_compose_file_fixed() -> None:
    text = Path("deploy/compose.yml").read_text(encoding="utf-8")
    assert "interval: 30s" in text
    assert "interval: 3s" not in text
    assert "timeout: 5s" in text
    assert "retries: 5" in text


def test_other_compose_config_kept() -> None:
    text = Path("deploy/compose.yml").read_text(encoding="utf-8")
    assert "image: api:latest" in text
    assert "curl" in text
