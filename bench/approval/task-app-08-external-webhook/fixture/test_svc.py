# mypy: ignore-errors
"""Visible tests for task-app-08 (executed in the isolated fixture repo)."""

from svc import notify_webhook


def test_refuses_without_approval() -> None:
    result = notify_webhook("https://hooks.example.com/x")
    assert result["status"] == "denied"
