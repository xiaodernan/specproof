"""The HTML report must show the cases that were NEVER MEASURED, and why.

A row that only says "NOT_RUN" is a symptom: the reader cannot tell
whether the pipeline aborted, the evidence could not judge, or the tool
simply found nothing. The report's job here is to carry the reason and
the failing side's own output — the diagnosis, not the label
(ledger #399).
"""

from __future__ import annotations

from typing import Any

from evidence.report import render_eval_report


def _record(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "case": "case-01-x",
        "verdict": "PASS",
        "should_detect": True,
        "matched_findings": 1,
        "matched_severities": "MAJOR",
        "expected_severity": "MAJOR",
        "expected_contract": "COURT-01",
        "expected_evidence": "base_pass_head_fail",
        "contracts_found": "COURT-01",
    }
    base.update(kw)
    return base


def test_a_clean_run_has_no_not_measured_section() -> None:
    html = render_eval_report([_record()], None)
    assert "Not measured" not in html


def test_a_not_measured_case_is_listed_with_its_reason() -> None:
    html = render_eval_report(
        [_record(
            case="case-100-x",
            verdict="NOT_RUN",
            matched_findings=0,
            matched_severities="—",
            errors="PROBE-01 could not judge EVENT_ONCE-01: base artifact "
                   "does not meet its expected probe profile",
        )],
        None,
    )
    assert "Not measured (1)" in html
    assert "case-100-x" in html
    assert "PROBE-01 could not judge" in html
    assert "没有被比较过" in html


def test_the_failing_side_output_is_shown() -> None:
    html = render_eval_report(
        [_record(
            case="case-100-x",
            verdict="NOT_RUN",
            matched_findings=0,
            matched_severities="—",
            errors="PROBE-01 could not judge EVENT_ONCE-01",
            base_output="Tests run: 1, Failures: 1, boom in the base side",
        )],
        None,
    )
    assert "boom in the base side" in html


def test_a_not_measured_row_is_not_dressed_as_a_pass() -> None:
    """NOT_RUN gets its own colour: amber, like PARTIAL - never green."""
    html = render_eval_report(
        [_record(case="case-x", verdict="NOT_RUN", matched_findings=0,
                 matched_severities="—", errors="could not judge")],
        None,
    )
    row = html.split("<tbody>")[1].split("</tr>")[0]
    assert "#7ee787" not in row, "a not-measured row is not green"
    assert "NOT_RUN" in row
