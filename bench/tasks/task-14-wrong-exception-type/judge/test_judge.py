# mypy: ignore-errors
"""Hidden judge tests for task-14: acceptance + no-regression guards."""

import pytest
from svc import safe_divide


def test_zero_numerator() -> None:
    assert safe_divide(0, 5) == 0.0


def test_type_error_propagates() -> None:
    with pytest.raises(TypeError):
        safe_divide("a", 2)


def test_negative_division() -> None:
    assert safe_divide(-6, 3) == -2.0
