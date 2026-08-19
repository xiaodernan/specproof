"""Minimal price-calculation module for the offline mutation sample.

Four real behaviors: bulk discount, free-shipping threshold, tax, and an
advisory tip suggestion. The tip behavior is deliberately OUTSIDE the spec
contract (spec/spec.md, "Out of scope") and has no test coverage: mutant M06
targets it and therefore survives, which keeps the offline kill-rate honest
(a real coverage gap is reported instead of a rigged 100% score).
"""

FREE_SHIPPING_THRESHOLD = 100.0
BULK_DISCOUNT_RATE = 0.10
TAX_RATE = 0.08
SUGGESTED_TIP_RATE = 0.15


def apply_bulk_discount(subtotal: float) -> float:
    """10% off, applied as multiplication, once the 500.0 threshold is reached."""
    if subtotal >= 500.0:
        return round(subtotal * (1.0 - BULK_DISCOUNT_RATE), 2)
    return subtotal


def is_free_shipping(subtotal: float) -> bool:
    """Orders at or above FREE_SHIPPING_THRESHOLD (exactly 100.0) ship free."""
    return subtotal >= FREE_SHIPPING_THRESHOLD


def with_tax(subtotal: float) -> float:
    """Subtotal plus 8% tax, rounded to cents."""
    return round(subtotal * (1.0 + TAX_RATE), 2)


def suggested_tip(subtotal: float) -> float:
    """Advisory tip amount (out of spec scope — see spec/spec.md)."""
    return round(subtotal * SUGGESTED_TIP_RATE, 2)
