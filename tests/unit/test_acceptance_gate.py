"""Offline unit tests for the acceptance gate (evidence/acceptance.py).

These are pure-count tests: no pipeline, no Docker, no model. The headline
regression they lock is the "vacuous 100%" bug the gate removes — an empty
or degenerate sample must never read as flawless accuracy, and a sample too
small to prove a floor must yield INSUFFICIENT, never PASS.
"""
from __future__ import annotations

from typing import Any

from evidence.acceptance import (
    FAIL,
    INSUFFICIENT,
    PASS,
    AcceptanceCriteria,
    MetricCounts,
    evaluate,
    fmt_metric,
    score,
    severity_match_of,
    severity_reconciliation,
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


# -- #188: ground-truth severity reconciliation ---------------------------


def _case(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "case": "case-x",
        "verdict": "PASS",
        "should_detect": True,
        "matched_findings": 1,
        "matched_severities": "BLOCKER",
        "expected_severity": "BLOCKER",
        "expected_contract": "AUTH-01",
    }
    base.update(kw)
    return base


def test_severity_agreement_is_exact_level_match_share() -> None:
    results = [
        _case(case="a", matched_severities="BLOCKER"),
        _case(case="b", matched_severities="BLOCKER"),
        _case(case="c", matched_severities="MAJOR", expected_severity="MAJOR"),
        _case(case="d", matched_severities="MINOR", expected_severity="MAJOR"),
    ]
    rec = severity_reconciliation(results)
    assert rec["severity_agreement"] == 75.0
    assert rec["matched_positive_cases"] == 4
    assert rec["severity_mismatch_cases"] == 1
    assert rec["mismatches"] == [
        {"case": "d", "expected": "MAJOR", "actual": "MINOR"}
    ]


def test_severity_match_triple_state_and_drift_detection() -> None:
    assert severity_match_of(_case()) is True
    assert (
        severity_match_of(
            _case(matched_severities="MINOR", expected_severity="MAJOR")
        )
        is False
    )
    assert (
        severity_match_of(_case(matched_findings=0, matched_severities="-"))
        is None
    )
    assert severity_match_of(_case(should_detect=False)) is None


def test_severity_metrics_none_when_no_level_call_made() -> None:
    results = [
        _case(
            case="miss",
            verdict="MISS",
            matched_findings=0,
            matched_severities="-",
        ),
        _case(
            case="neg",
            should_detect=False,
            verdict="PASS",
            matched_findings=0,
            matched_severities="-",
        ),
    ]
    rec = severity_reconciliation(results)
    assert rec["severity_agreement"] is None
    assert rec["severe_precision"] is None


def test_severe_precision_denominator_covers_drift_and_false_positives() -> None:
    results = [
        # Severe positives: 3 in the domain - 2 exact, 1 downgraded to MINOR.
        _case(case="a"),
        _case(case="b"),
        _case(case="c", expected_severity="MAJOR", matched_severities="MINOR"),
        # A negative that produced a confirmed finding: a severe-call FP.
        _case(
            case="neg",
            should_detect=False,
            verdict="FALSE_POSITIVE",
            matched_findings=0,
            matched_severities="-",
        ),
        # A matched positive expecting a low severity: never a severe call,
        # so it stays out of the denominator entirely.
        _case(case="low", expected_severity="MINOR", matched_severities="MINOR"),
    ]
    rec = severity_reconciliation(results)
    # TP=2; denominator = 3 severe positives + 1 FP negative = 4.
    assert rec["severe_precision"] == 50.0
    assert rec["severe_call_positives"] == 3
    assert rec["severe_true_positives"] == 2
    assert rec["severe_false_positives"] == 1
    # Agreement still judges every matched positive, including "low".
    assert rec["matched_positive_cases"] == 4


def test_perfect_level_calls_score_exactly_hundred() -> None:
    rec = severity_reconciliation([_case(case="a"), _case(case="b")])
    assert rec["severity_agreement"] == 100.0
    assert rec["severe_precision"] == 100.0


def test_multi_value_severities_count_as_drift_not_crash() -> None:
    assert severity_match_of(_case(matched_severities="BLOCKER, MAJOR")) is False
