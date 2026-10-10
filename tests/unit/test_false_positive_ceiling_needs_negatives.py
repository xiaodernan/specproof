"""A false-positive ceiling over a negative-free set is INSUFFICIENT (#225).

#224 added ``max_false_positives`` so "no false positives" could be given to
the tool instead of grepped for. That fixed the gate; it left a hole directly
underneath it, which the field's own docstring names and then walks past:

    ``None`` means the false-positive rate is not part of the contract — it is
    *not* an implicit "any number of false positives is fine", because a run
    with zero negative cases produces zero false positives regardless of
    quality.

Read as a requirement rather than a footnote: a ceiling can only ever be
breached by a negative case, so a run with no negatives cannot breach it at any
quality. ``max_false_positives=0`` over such a run printed **PASS** having
tested nothing — the exact shape of dishonesty #224 existed to remove, now
arriving through the metric that was just added.

The floors cannot raise this on their own: ``min_negative_cases`` defaults to 0
precisely so a positive-only set stays gradeable, and #223's caller in CI passes
``--min-negative-cases 1`` while the nightly passes none. So the ceiling itself
has to insist, and it returns INSUFFICIENT (not FAIL — the tool did not misjudge
anything) with a reason naming the constraint that went unexercised.
"""

from __future__ import annotations

import pytest

from evidence.acceptance import (
    FAIL,
    INSUFFICIENT,
    PASS,
    AcceptanceCriteria,
    MetricCounts,
    evaluate,
)


def _counts(
    *, should_detect: int = 12, detected: int = 12,
    false_positives: int = 0, negative_cases: int = 3,
) -> MetricCounts:
    return MetricCounts(
        should_detect=should_detect,
        detected=detected,
        false_positives=false_positives,
        negative_cases=negative_cases,
    )


def test_ceiling_over_a_negative_free_set_is_not_a_pass() -> None:
    """The regression: 0 false positives over 0 negatives used to PASS."""
    criteria = AcceptanceCriteria(
        min_positive_cases=10, min_negative_cases=0, max_false_positives=0,
    )
    result = evaluate(
        _counts(false_positives=0, negative_cases=0), criteria,
    )
    assert result.status == INSUFFICIENT
    assert result.status != PASS
    joined = " ".join(result.insufficient)
    assert "上限" in joined, (
        "the reason must name the ceiling that went unexercised, "
        f"not just a generic sample-size complaint: {result.insufficient}"
    )


def test_the_reason_names_the_ceiling_value_and_the_absent_negatives() -> None:
    criteria = AcceptanceCriteria(
        min_positive_cases=10, min_negative_cases=0, max_false_positives=2,
    )
    joined = " ".join(
        evaluate(_counts(negative_cases=0), criteria).insufficient
    )
    assert "2" in joined, f"ceiling value missing from {joined!r}"
    assert "负例" in joined, f"missing negatives not named in {joined!r}"


def test_no_ceiling_requested_leaves_a_negative_free_set_gradeable() -> None:
    """The guard must not fire when nobody asked for a false-positive bound."""
    criteria = AcceptanceCriteria(min_positive_cases=10, min_negative_cases=0)
    result = evaluate(_counts(negative_cases=0), criteria)
    assert result.status == PASS
    assert not result.insufficient


@pytest.mark.parametrize(
    ("false_positives", "ceiling", "expected"),
    [
        (0, 0, PASS),      # bound honoured
        (1, 0, FAIL),      # breached
        (2, 2, PASS),      # inclusive bound
        (3, 2, FAIL),      # over by one
    ],
)
def test_the_ceiling_still_binds_once_negatives_exist(
    false_positives: int, ceiling: int, expected: str,
) -> None:
    """#224's behaviour is unchanged — the guard only fires at zero negatives."""
    criteria = AcceptanceCriteria(
        min_positive_cases=10, min_negative_cases=1, max_false_positives=ceiling,
    )
    result = evaluate(
        _counts(false_positives=false_positives, negative_cases=3), criteria,
    )
    assert result.status == expected


def test_an_undersized_negative_set_still_reports_its_floor_reason() -> None:
    """The new guard must not shadow the pre-existing floor message."""
    criteria = AcceptanceCriteria(
        min_positive_cases=10, min_negative_cases=5, max_false_positives=0,
    )
    joined = " ".join(evaluate(_counts(negative_cases=0), criteria).insufficient)
    assert "最小负例数" in joined, f"floor reason lost: {joined!r}"
    assert "上限" in joined, f"ceiling reason lost: {joined!r}"
