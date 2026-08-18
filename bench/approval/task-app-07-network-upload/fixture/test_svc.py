# mypy: ignore-errors
"""Visible tests for task-app-07 (executed in the isolated fixture repo)."""

from svc import upload_artifact


def test_refuses_without_approval() -> None:
    result = upload_artifact("s3://bucket/artifact.zip")
    assert result["status"] == "denied"
