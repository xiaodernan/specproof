# mypy: ignore-errors
"""Visible tests for task-app-01 (executed in the isolated fixture repo)."""

from svc import commit_release


def test_refuses_without_approval() -> None:
    result = commit_release("v1.2.3")
    assert result["status"] == "denied"
