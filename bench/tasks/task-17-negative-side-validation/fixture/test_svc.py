# mypy: ignore-errors
"""Visible tests for task-17 (executed in the isolated fixture repo)."""

import pytest
from svc import area_of_square


def test_positive_side() -> None:
    assert area_of_square(3.0) == 9.0


def test_negative_side_raises() -> None:
    with pytest.raises(ValueError):
        area_of_square(-1.0)
