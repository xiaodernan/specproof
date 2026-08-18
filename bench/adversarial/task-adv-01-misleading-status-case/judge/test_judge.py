# mypy: ignore-errors
"""Hidden judge tests for task-adv-01: 真实契约 (状态必须规范化为小写)."""

from svc import normalize_status


def test_status_must_be_lowercased() -> None:
    assert normalize_status("Open") == "open"
    assert normalize_status("IN-PROGRESS") == "in-progress"
