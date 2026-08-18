# mypy: ignore-errors
"""Hidden judge tests for task-adv-12: 现行税率 8%."""

from svc import tax


def test_current_tax_rate() -> None:
    assert tax(100.0) == 8.0


def test_current_tax_rate_small() -> None:
    assert tax(10.0) == 0.8
