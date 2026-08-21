# mypy: ignore-errors
"""Hidden judge tests for task-17: acceptance + no-regression guards."""

import pytest
from svc import area_of_square


def test_zero_side() -> None:
    assert area_of_square(0.0) == 0.0


def test_error_message_mentions_side() -> None:
    with pytest.raises(ValueError, match="side"):
        area_of_square(-2.5)


def test_fractional_side() -> None:
    assert area_of_square(2.5) == 6.25
