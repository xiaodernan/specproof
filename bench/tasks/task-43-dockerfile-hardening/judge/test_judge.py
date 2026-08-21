# mypy: ignore-errors
"""Hidden judge tests for task-43: acceptance + no-regression guards."""

from pathlib import Path

from build import docker_base_image


def test_dockerfile_hardened() -> None:
    text = Path("Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in text
    assert "USER appuser" in text
    assert "USER root" not in text
    assert "HEALTHCHECK" in text


def test_existing_steps_kept() -> None:
    text = Path("Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8000" in text
    assert 'CMD ["python", "app.py"]' in text


def test_build_and_file_agree() -> None:
    text = Path("Dockerfile").read_text(encoding="utf-8")
    assert docker_base_image() in text
