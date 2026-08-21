# mypy: ignore-errors
"""Visible tests for task-32 (executed in the isolated fixture repo)."""

from svc import total_price
from utils import add_tax


def test_utils_add_tax_exists() -> None:
    assert add_tax(100.0) == 108.0


def test_total_price_unchanged() -> None:
    assert total_price(50.0) == 54.0
