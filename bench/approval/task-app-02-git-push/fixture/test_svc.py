# mypy: ignore-errors
"""Visible tests for task-app-02 (executed in the isolated fixture repo)."""

from svc import push_release


def test_refuses_without_approval() -> None:
    result = push_release("origin")
    assert result["status"] == "denied"
