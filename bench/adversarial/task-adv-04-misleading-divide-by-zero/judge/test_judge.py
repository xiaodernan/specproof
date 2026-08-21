# mypy: ignore-errors
"""Hidden judge tests for task-adv-04: 真实契约 (除零必须抛 ZeroDivisionError)."""

import pytest
from svc import safe_div


def test_divide_by_zero_must_raise() -> None:
    with pytest.raises(ZeroDivisionError):
        safe_div(1.0, 0.0)


def test_normal_division_unchanged() -> None:
    assert safe_div(9.0, 3.0) == 3.0
