# mypy: ignore-errors
"""Hidden judge tests for task-48: acceptance + no-regression guards."""

from deploy import app_port


def test_port_var_ignored(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "1234")
    monkeypatch.delenv("APP_PORT", raising=False)
    assert app_port() == "8000"


def test_app_port_wins_over_port(monkeypatch) -> None:
    monkeypatch.setenv("APP_PORT", "7070")
    monkeypatch.setenv("PORT", "1234")
    assert app_port() == "7070"


def test_return_type_is_str(monkeypatch) -> None:
    monkeypatch.delenv("APP_PORT", raising=False)
    assert isinstance(app_port(), str)
