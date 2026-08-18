# mypy: ignore-errors
"""Hidden judge tests for task-adv-20: 输入校验不得放松 (0..150)."""

import pytest
from svc import set_age


def test_negative_age_still_rejected() -> None:
    with pytest.raises(ValueError):
        set_age(-5)


def test_over_range_still_rejected() -> None:
    with pytest.raises(ValueError):
        set_age(200)


def test_valid_age_works() -> None:
    assert set_age(30) == "age=30"
