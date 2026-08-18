# mypy: ignore-errors
"""Visible tests for task-26 (executed in the isolated fixture repo)."""

from api import host_from_env


def test_env_value_wins() -> None:
    assert host_from_env({"HOST": "10.0.0.9"}) == "10.0.0.9"


def test_default_used_when_missing() -> None:
    assert host_from_env({}) == "127.0.0.1"
