# mypy: ignore-errors
"""Visible tests for task-45 (executed in the isolated fixture repo)."""

from build import compose_healthcheck


def test_healthcheck_contract() -> None:
    assert compose_healthcheck() == {"interval": "30s", "timeout": "5s", "retries": 5}
