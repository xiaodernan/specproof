# mypy: ignore-errors
"""Visible tests for task-48 (executed in the isolated fixture repo)."""

from deploy import app_port


def test_app_port_env_var(monkeypatch) -> None:
    monkeypatch.setenv("APP_PORT", "9090")
    assert app_port() == "9090"


def test_default_port(monkeypatch) -> None:
    monkeypatch.delenv("APP_PORT", raising=False)
    assert app_port() == "8000"
