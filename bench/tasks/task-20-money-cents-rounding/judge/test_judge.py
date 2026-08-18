# mypy: ignore-errors
"""Hidden judge tests for task-20: acceptance + no-regression guards."""

from svc import to_cents


def test_half_up_rounding() -> None:
    assert to_cents(2.675) == 268


def test_binary_sum() -> None:
    assert to_cents(0.1 + 0.2) == 30


def test_negative_amount() -> None:
    assert to_cents(-0.01) == -1


def test_large_amount() -> None:
    assert to_cents(123456.78) == 12345678
