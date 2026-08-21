"""Differential test channel for the offline mutation sample.

Each assertion documents which hand-defined mutant it is expected to kill
(see mutants/manifest.json). The 100.0 free-shipping boundary is deliberately
NOT probed here: the contract checker owns the exact threshold, so mutant M04
is killed by the SpecProof verdict alone — the demo point of this sample.
"""

from module.pricing import apply_bulk_discount, is_free_shipping, with_tax


def test_bulk_discount_applies_at_threshold() -> None:
    # Kills M02 (boundary change >= -> >): the exact threshold must discount.
    assert apply_bulk_discount(500.0) == 450.0
    # Kills M01 (operand swap * -> +): multiplication is the required operation.
    assert apply_bulk_discount(600.0) == 540.0


def test_bulk_discount_below_threshold_unchanged() -> None:
    assert apply_bulk_discount(100.0) == 100.0


def test_free_shipping_away_from_boundary() -> None:
    # Kills M03 (return inversion >= -> <=): above ships free, below does not.
    assert is_free_shipping(150.0) is True
    assert is_free_shipping(50.0) is False


def test_tax_applied_as_multiplication() -> None:
    # Kills M05 (constant change 0.08 -> 0.18).
    assert with_tax(100.0) == 108.0
    assert with_tax(0.0) == 0.0
