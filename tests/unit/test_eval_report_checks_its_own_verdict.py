"""The page must not contradict itself - and it must CHECK.

The acceptance card carries the verdict the RUN decided. The numbers on
the page are recomputed from the case records. If those two disagree,
the page shows a verdict next to numbers that contradict it - and a
reader cannot tell which one to believe.

Before #414 the report's own numbers were 169.7% recall (it counted
NEGATIVE cases as detections) sitting right next to a PASS verdict. The
contradiction was invisible because nothing compared the two.

So the page checks itself now: it recomputes the acceptance from its own
records and the same criteria, and says so LOUDLY when the two disagree
(ledger #416).

These tests are SHARP: reverting the check makes the first one fail.
"""

from __future__ import annotations

from typing import Any

from evidence.acceptance import (
    AcceptanceCriteria,
    MetricCounts,
    evaluate,
)
from evidence.report import render_eval_report


def _record(case: str, *, verdict: str = "PASS", should_detect: bool = True) -> dict[str, Any]:
    detected = verdict in ("PASS", "PARTIAL")
    return {
        "case": case,
        "verdict": verdict,
        "should_detect": should_detect,
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 1 if detected else 0,
        "matched_severities": "MAJOR" if detected else "",
        "contract_level": "MAJOR" if detected else "",
        "contracts_found": "COURT-01" if detected else "",
        "finding_evidence": (
            [{"contract_id": "COURT-01", "severity": "MAJOR",
              "evidence_type": "base_pass_head_fail"}]
            if detected
            else []
        ),
    }


def _criteria() -> AcceptanceCriteria:
    return AcceptanceCriteria(
        min_recall=95.0,
        min_precision=95.0,
        min_f1=95.0,
        max_false_positives=0,
        min_positive_cases=1,
        min_negative_cases=1,
    )


def test_a_page_whose_verdict_matches_its_numbers_says_nothing() -> None:
    """The normal case: the page must NOT cry wolf."""
    records = [
        _record("case-01"),
        _record("case-02"),
        _record("case-03", should_detect=False),
    ]
    counts = MetricCounts(
        should_detect=2, detected=2, false_positives=0, negative_cases=1
    )
    acceptance = evaluate(counts, _criteria())
    html = render_eval_report(records, acceptance)
    assert "互相矛盾" not in html
    assert acceptance.status == "PASS"


def test_a_page_whose_verdict_contradicts_its_numbers_says_so() -> None:
    """The guard fires.

    Sharp: without the check the page would show a PASS card next to
    numbers that fail the same criteria, and say nothing.
    """
    records = [
        _record("case-01"),
        _record("case-02", verdict="MISS"),
        _record("case-03", should_detect=False),
    ]
    # A verdict that says PASS although the records say the recall is 50%.
    counts = MetricCounts(
        should_detect=2, detected=2, false_positives=0, negative_cases=1
    )
    acceptance = evaluate(counts, _criteria())
    assert acceptance.status == "PASS"

    html = render_eval_report(records, acceptance)
    assert "互相矛盾" in html, html[-3000:]
    assert "PASS" in html
    assert "FAIL" in html


def test_a_page_with_no_verdict_never_claims_a_contradiction() -> None:
    """A run that was killed carries no verdict - there is nothing to
    contradict."""
    records = [_record("case-01"), _record("case-02", verdict="MISS")]
    html = render_eval_report(records, None)
    assert "互相矛盾" not in html


def test_the_check_uses_the_sidecars_own_criteria() -> None:
    """The check does not invent its own thresholds.

    A verdict that is INSUFFICIENT because the sample is too small must
    not be reported as a contradiction when the page's numbers produce
    the same INSUFFICIENT.
    """
    records = [_record("case-01")]
    criteria = AcceptanceCriteria(
        min_recall=95.0,
        min_positive_cases=10,   # the sample is too small
    )
    counts = MetricCounts(
        should_detect=1, detected=1, false_positives=0, negative_cases=0
    )
    acceptance = evaluate(counts, criteria)
    assert acceptance.status == "INSUFFICIENT"
    html = render_eval_report(records, acceptance)
    assert "互相矛盾" not in html, html[-2000:]
