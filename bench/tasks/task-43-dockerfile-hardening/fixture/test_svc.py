# mypy: ignore-errors
"""Visible tests for task-43 (executed in the isolated fixture repo)."""

from build import docker_base_image


def test_base_image() -> None:
    assert docker_base_image() == "python:3.12-slim"
