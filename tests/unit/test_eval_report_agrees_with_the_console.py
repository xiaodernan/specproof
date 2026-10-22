"""The HTML report and the console must not disagree about the same run.

Ledger #414 found THREE disagreements between the two artifacts, all of
them measured, not guessed:

1. **The report published an impossible recall.** It counted NEGATIVE
   cases (whose verdict is PASS) as detections, so the real 56-record run
   showed "Recall 169.7%" and "F1 125.8%" on the page while the console
   said 100.0%. The report also put never-measured cases in the recall
   DENOMINATOR while its own "Not Measured" stat said they were out of
   it. The counting rule is now the run's rule (``counter_deltas``), used
   by both.

2. **The retry story was only in the console.** A reader of the artifact
   could not tell a wobbling detection from a case that was never
   measured.

3. **A case that was missed EVERY time was called "unstable
   detection".** There was no detection to wobble. The retry reason is
   now classified by ONE rule with FOUR outcomes.

These tests are SHARP: reverting any of the fixes makes them fail.
"""

from __future__ import annotations

import re
from typing import Any

from evidence.acceptance import (
    RETRY_CONSISTENTLY_MISSED,
    RETRY_FIRST_ATTEMPT_UNJUDGED,
    RETRY_NEVER_MEASURED,
    RETRY_UNSTABLE_DETECTION,
    count_records,
    retry_reason,
    retry_summary,
)
from evidence.report import render_eval_report


def _record(
    case: str,
    *,
    verdict: str = "PASS",
    should_detect: bool = True,
    attempts: int = 1,
    first_attempt_verdict: str | None = None,
) -> dict[str, Any]:
    detected = verdict in ("PASS", "PARTIAL")
    record: dict[str, Any] = {
        "case": case,
        "verdict": verdict,
        "should_detect": should_detect,
        "duration_ms": 1000,
        "attempts": attempts,
        "first_attempt_verdict": (
            first_attempt_verdict if first_attempt_verdict is not None else verdict
        ),
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 1 if detected else 0,
        "matched_severities": "MAJOR" if detected else "",
        "contract_level": "MAJOR" if detected else "",
        "all_matched_severities": "MAJOR" if detected else "",
        "contracts_found": "COURT-01" if detected else "",
        "finding_evidence": (
            [
                {
                    "contract_id": "COURT-01",
                    "severity": "MAJOR",
                    "evidence_type": "base_pass_head_fail",
                }
            ]
            if detected
            else []
        ),
    }
    return record


def _stat(html: str, label: str) -> str:
    """The value of the stat box with this label."""
    match = re.search(
        r'<div class="value"[^>]*>([^<]*)</div>\s*<div class="label">'
        + re.escape(label)
        + r"</div>",
        html,
    )
    assert match is not None, f"no stat box labelled {label!r}"
    return match.group(1)


# -- 1. the report's numbers are the run's numbers --------------------------


def test_a_negative_case_is_not_a_detection_in_the_report() -> None:
    """A negative case's verdict is PASS - it is NOT a detection.

    Sharp: with the report's own inline counting this case was counted
    as a detection and the recall came out ABOVE 100%.
    """
    records = [
        _record("case-01"),
        _record("case-02"),
        _record("case-03", verdict="MISS"),
        _record("case-04", should_detect=False),
    ]
    html = render_eval_report(records, None)
    assert _stat(html, "Recall") == "66.7%", html[:2000]
    assert _stat(html, "Detected / Should Detect") == "2/3"


def test_a_never_measured_case_is_out_of_the_recall_denominator() -> None:
    """The report's own "Not Measured" stat and its recall must agree.

    Sharp: with the inline counting the never-measured case was in the
    denominator, so the page said "out of the denominator" (in the stat)
    and put it in (in the ratio).
    """
    records = [
        _record("case-01"),
        _record("case-02"),
        _record("case-03", verdict="NOT_RUN"),
    ]
    html = render_eval_report(records, None)
    assert _stat(html, "Not Measured") == "1"
    assert _stat(html, "Recall") == "100.0%", html[:2000]
    # The never-measured case is in NEITHER side: 2 detected out of 2 that
    # were compared (not 2 out of 3).
    assert _stat(html, "Detected / Should Detect") == "2/2"


def test_the_report_and_the_counting_rule_agree() -> None:
    """The report's numbers come from the run's counting rule."""
    records = [
        _record("case-01"),
        _record("case-02", verdict="MISS"),
        _record("case-03", should_detect=False),
        _record("case-04", should_detect=False, verdict="FALSE_POSITIVE"),
    ]
    counts, not_measured = count_records(records)
    html = render_eval_report(records, None)
    assert _stat(html, "Detected / Should Detect") == (
        f"{counts.detected}/{counts.should_detect}"
    )
    assert _stat(html, "Not Measured") == str(not_measured)
    assert _stat(html, "False Positives") == str(counts.false_positives)


def test_the_recall_on_the_page_can_never_exceed_a_hundred() -> None:
    """A recall above 100% is not a metric - it is a counting bug.

    This is the property the 169.7% broke.
    """
    records = [
        _record("case-01"),
        _record("case-02"),
        _record("case-03", should_detect=False),
        _record("case-04", should_detect=False),
    ]
    html = render_eval_report(records, None)
    recall = _stat(html, "Recall")
    assert recall.endswith("%")
    assert float(recall.rstrip("%")) <= 100.0, recall


# -- 2. the retry story is in the report too --------------------------------


def test_the_report_says_how_many_cases_were_measured_more_than_once() -> None:
    records = [
        _record("case-01"),
        _record("case-02", attempts=3, first_attempt_verdict="NOT_RUN"),
    ]
    html = render_eval_report(records, None)
    assert _stat(html, "Measured More Than Once") == "1"
    assert "Measured more than once (1)" in html
    assert "case-02" in html


def test_a_run_with_no_retries_says_zero() -> None:
    html = render_eval_report([_record("case-01")], None)
    assert _stat(html, "Measured More Than Once") == "0"
    assert "Measured more than once" not in html


# -- 3. four reasons, not three ---------------------------------------------


def test_a_case_missed_every_time_is_not_an_unstable_detection() -> None:
    """There was NO detection to wobble.

    Sharp: with the three-way rule this case was called "unstable
    detection" - the label claims the detection changed its mind about a
    run that never detected anything.
    """
    record = _record("case-01", verdict="MISS", attempts=3,
                      first_attempt_verdict="MISS")
    assert retry_reason(record) == RETRY_CONSISTENTLY_MISSED
    html = render_eval_report([record], None)
    assert "consistently missed" in html
    assert "unstable detection" not in html


def test_the_four_reasons_are_four_different_things() -> None:
    cases = {
        RETRY_NEVER_MEASURED: _record("a", verdict="NOT_RUN", attempts=3,
                                      first_attempt_verdict="NOT_RUN"),
        RETRY_FIRST_ATTEMPT_UNJUDGED: _record("b", verdict="MISS", attempts=3,
                                              first_attempt_verdict="NOT_RUN"),
        RETRY_CONSISTENTLY_MISSED: _record("c", verdict="MISS", attempts=3,
                                            first_attempt_verdict="MISS"),
        RETRY_UNSTABLE_DETECTION: _record("d", verdict="PASS", attempts=2,
                                          first_attempt_verdict="MISS"),
    }
    reasons = {retry_reason(rec) for rec in cases.values()}
    assert reasons == set(cases), reasons
    # and each reason is the one the rule says it is
    for expected, record in cases.items():
        assert retry_reason(record) == expected


def test_a_detection_that_really_wobbled_is_still_called_that() -> None:
    record = _record("case-01", verdict="PASS", attempts=2,
                      first_attempt_verdict="MISS")
    assert retry_reason(record) == RETRY_UNSTABLE_DETECTION
    html = render_eval_report([record], None)
    assert "unstable detection" in html


def test_the_summary_counts_each_reason_separately() -> None:
    records = [
        _record("a", verdict="NOT_RUN", attempts=3, first_attempt_verdict="NOT_RUN"),
        _record("b", verdict="MISS", attempts=3, first_attempt_verdict="NOT_RUN"),
        _record("c", verdict="MISS", attempts=3, first_attempt_verdict="MISS"),
        _record("d", verdict="PASS", attempts=2, first_attempt_verdict="MISS"),
        _record("e"),
    ]
    summary = retry_summary(records)
    assert summary["retried_cases"] == 4
    assert summary["by_reason"] == {
        RETRY_NEVER_MEASURED: 1,
        RETRY_FIRST_ATTEMPT_UNJUDGED: 1,
        RETRY_CONSISTENTLY_MISSED: 1,
        RETRY_UNSTABLE_DETECTION: 1,
    }
    assert [entry["case"] for entry in summary["retries"]] == ["a", "b", "c", "d"]
