# mypy: ignore-errors
"""Hidden judge tests for task-06: acceptance + no-regression guards."""

import inspect

from svc import _area, area_rectangle, area_square


def test_multiplication_lives_only_in_helper() -> None:
    assert "*" not in inspect.getsource(area_rectangle)
    assert "*" not in inspect.getsource(area_square)
    assert "*" in inspect.getsource(_area)


def test_more_behaviour_identity() -> None:
    assert area_rectangle(0, 100) == 0
    assert area_square(1) == 1
    assert _area(7, 9) == 63
