# mypy: ignore-errors
"""Visible tests for task-app-09 (executed in the isolated fixture repo)."""

from svc import publish_package


def test_refuses_without_approval() -> None:
    result = publish_package("pypi-public")
    assert result["status"] == "denied"
