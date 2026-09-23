"""Offline unit tests for the acceptance gate (evidence/acceptance.py).

These are pure-count tests: no pipeline, no Docker, no model. The headline
regression they lock is the "vacuous 100%" bug the gate removes — an empty
or degenerate sample must never read as flawless accuracy, and a sample too
small to prove a floor must yield INSUFFICIENT, never PASS.
"""
from __future__ import annotations

from evidence.acceptance import (
    FAIL,
    INSUFFICIENT,
    PASS,
    AcceptanceCriteria,
    MetricCounts,
    evaluate,
    fmt_metric,
    score,
)


def test_recall_precision_f1_match_historical_formulas_when_defined() -> None:
    counts = MetricCounts(
        should_detect=10, detected=8, false_positives=2, negative_cases=10
    )
    m = score(counts)
    assert m.recall == 80.0          # 8 / 10
    assert m.precision == 80.0       # 8 / (8 + 2)
    assert m.f1 == 80.0              # harmonic mean of equal P/R


def test_empty_positive_sample_gives_none_not_100() -> None:
    # The exact bug: should_detect == 0 used to yield recall == 100.0.
    m = score(MetricCounts(should_detect=0, detected=0, false_positives=0))
    assert m.recall is None
    assert m.recall_any is None
    # precision denominator (detected + false_positives) is also 0 -> None.
    assert m.precision is None
    # F1 needs both sides defined; neither is -> None, not a fake score.
    assert m.f1 is None


def test_all_false_positives_gives_zero_precision_not_none() -> None:
    # detected == 0 but false_positives > 0: denominator > 0 so precision is
    # a real 0.0 (correctly terrible), while recall stays None (no positives).
    m = score(MetricCounts(should_detect=0, detected=0, false_positives=3))
    assert m.precision == 0.0
    assert m.recall is None
    assert m.f1 is None


def test_f1_zero_when_both_metrics_defined_but_zero() -> None:
    m = score(
        MetricCounts(should_detect=5, detected=0, false_positives=2, negative_cases=5)
    )
    assert m.recall == 0.0
    assert m.precision == 0.0
    assert m.f1 == 0.0  # defined-and-zero, distinct from None (undefined)


def test_fmt_metric_never_renders_none_as_a_number() -> None:
    assert fmt_metric(None) == "无法评估 (n=0)"
    assert fmt_metric(80.0) == "80.0%"
    assert fmt_metric(None, undefined="样本不足") == "样本不足 (n=0)"


def test_evaluate_insufficient_when_sample_too_small() -> None:
    # Even trivially perfect metrics cannot PASS on an under-sized sample.
    criteria = AcceptanceCriteria(min_positive_cases=10, min_negative_cases=5)
    result = evaluate(
        MetricCounts(should_detect=1, detected=1, false_positives=0, negative_cases=1),
        criteria,
    )
    assert result.status == INSUFFICIENT
    assert not result.passed
    assert any("正例" in r for r in result.insufficient)
    assert any("负例" in r for r in result.insufficient)


def test_evaluate_empty_positive_set_is_insufficient_not_pass() -> None:
    # Regression: a run that detected everything in an EMPTY positive set must
    # NOT be a vacuous PASS.
    criteria = AcceptanceCriteria(min_positive_cases=10, min_negative_cases=0)
    result = evaluate(MetricCounts(should_detect=0, detected=0, false_positives=0), criteria)
    assert result.status == INSUFFICIENT


def test_evaluate_pass_when_floors_met_and_sample_sufficient() -> None:
    criteria = AcceptanceCriteria(
        min_recall=75.0, min_precision=75.0, min_positive_cases=10, min_negative_cases=5
    )
    result = evaluate(
        MetricCounts(should_detect=10, detected=9, false_positives=1, negative_cases=5),
        criteria,
    )
    assert result.status == PASS
    assert result.passed
    assert result.failures == []


def test_evaluate_fail_below_floor() -> None:
    criteria = AcceptanceCriteria(
        min_recall=90.0, min_precision=90.0, min_positive_cases=10, min_negative_cases=5
    )
    result = evaluate(
        MetricCounts(should_detect=10, detected=6, false_positives=4, negative_cases=6),
        criteria,
    )
    assert result.status == FAIL
    assert any("recall" in r for r in result.failures)
    assert any("precision" in r for r in result.failures)


def test_evaluate_fail_when_a_floor_is_set_but_metric_undefined() -> None:
    # Sample has enough negatives to be "sufficient" on that axis but zero
    # positives; a recall floor therefore cannot be met (undefined != pass).
    criteria = AcceptanceCriteria(
        min_recall=50.0, min_positive_cases=0, min_negative_cases=0
    )
    result = evaluate(
        MetricCounts(should_detect=0, detected=0, false_positives=1, negative_cases=3),
        criteria,
    )
    assert result.status == FAIL
    assert any("无法评估" in r for r in result.failures)


def test_default_criteria_enforces_only_sample_sufficiency() -> None:
    # The shipped default pins no numeric floors (they must be a deliberate,
    # maintainer-set choice), only sample sizes.
    d = AcceptanceCriteria.default()
    assert d.min_recall is None
    assert d.min_precision is None
    assert d.min_positive_cases == 10
    assert d.min_negative_cases == 5
    # So a sufficient sample with no floors always PASSES, but a small one
    # is still INSUFFICIENT — you cannot certify on an empty set.
    ok = evaluate(
        MetricCounts(should_detect=12, detected=3, false_positives=9, negative_cases=6),
        d,
    )
    assert ok.status == PASS
    small = evaluate(
        MetricCounts(should_detect=2, detected=2, false_positives=0, negative_cases=6),
        d,
    )
    assert small.status == INSUFFICIENT


def test_result_to_dict_is_json_safe_with_nulls() -> None:
    import json

    result = evaluate(
        MetricCounts(should_detect=0, detected=0, false_positives=0, negative_cases=0),
        AcceptanceCriteria(min_positive_cases=10),
    )
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["status"] == INSUFFICIENT
    assert payload["metrics"]["recall"] is None
    assert payload["counts"]["should_detect"] == 0
