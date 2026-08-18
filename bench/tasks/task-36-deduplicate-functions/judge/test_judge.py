# mypy: ignore-errors
"""Hidden judge tests for task-36: acceptance + no-regression guards."""

import pytest
from svc import sum_even, sum_odd, sum_parity


def test_invalid_parity_raises() -> None:
    with pytest.raises(ValueError):
        sum_parity([1], "prime")


def test_wrappers_delegate() -> None:
    values = [5, 6, 7, 8]
    assert sum_even(values) == sum_parity(values, "even")
    assert sum_odd(values) == sum_parity(values, "odd")


def test_negative_values() -> None:
    assert sum_parity([-2, -1, 0, 1], "even") == -2
