# mypy: ignore-errors
"""Visible tests for task-app-04 (executed in the isolated fixture repo)."""

from svc import push_tag


def test_refuses_without_approval() -> None:
    result = push_tag("v2.0.0")
    assert result["status"] == "denied"
