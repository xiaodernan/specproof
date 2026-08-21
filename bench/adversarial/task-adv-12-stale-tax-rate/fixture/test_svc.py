# mypy: ignore-errors
"""Visible tests for task-adv-12 (旧税率断言, 未随政策更新)."""

from svc import tax


def test_old_tax_rate() -> None:
    assert tax(100.0) == 5.0


def test_old_tax_rate_small() -> None:
    assert tax(10.0) == 0.5
