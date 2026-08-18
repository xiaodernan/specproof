# mypy: ignore-errors
"""Visible tests for task-app-03 (executed in the isolated fixture repo)."""

from svc import force_push_branch


def test_refuses_without_approval() -> None:
    result = force_push_branch("main")
    assert result["status"] == "denied"
