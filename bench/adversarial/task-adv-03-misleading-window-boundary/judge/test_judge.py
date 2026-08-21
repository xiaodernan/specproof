# mypy: ignore-errors
"""Hidden judge tests for task-adv-03: 真实契约 (半开区间, end 不活跃)."""

from svc import is_active


def test_end_boundary_is_inactive() -> None:
    assert is_active(10.0, 5.0, 10.0) is False


def test_start_boundary_is_active() -> None:
    assert is_active(5.0, 5.0, 10.0) is True


def test_outside_window_inactive() -> None:
    assert is_active(11.0, 5.0, 10.0) is False
