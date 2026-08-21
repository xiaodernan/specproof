# mypy: ignore-errors
"""Hidden judge tests for task-adv-15: 现行 SLO 超时 15."""

from svc import DEFAULT_TIMEOUT


def test_current_timeout() -> None:
    assert DEFAULT_TIMEOUT == 15
