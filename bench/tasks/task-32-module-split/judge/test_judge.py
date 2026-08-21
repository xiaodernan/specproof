# mypy: ignore-errors
"""Hidden judge tests for task-32: acceptance + no-regression guards."""

import inspect

import svc
from utils import add_tax


def test_no_duplicate_definition_in_svc() -> None:
    source = inspect.getsource(svc)
    assert "def add_tax" not in source


def test_rounding_semantics() -> None:
    assert add_tax(19.99) == 21.59
    assert add_tax(0.0) == 0.0


def test_total_price_uses_shared_helper() -> None:
    assert svc.total_price(10.0) == add_tax(10.0)
