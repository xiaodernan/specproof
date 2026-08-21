# mypy: ignore-errors
"""Visible tests for task-app-05 (executed in the isolated fixture repo)."""

from svc import delete_remote_branch


def test_refuses_without_approval() -> None:
    result = delete_remote_branch("feature/old")
    assert result["status"] == "denied"
