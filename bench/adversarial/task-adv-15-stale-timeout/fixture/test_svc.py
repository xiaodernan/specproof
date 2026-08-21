# mypy: ignore-errors
"""Visible tests for task-adv-15 (旧超时断言, 未随 SLO 更新)."""

from svc import DEFAULT_TIMEOUT


def test_old_timeout() -> None:
    assert DEFAULT_TIMEOUT == 30
