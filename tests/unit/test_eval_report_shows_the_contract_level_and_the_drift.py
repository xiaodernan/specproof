"""The HTML report must say the same thing about a contract's level as
the matrix does - and it must show WHICH cases drifted and WHY.

Two gaps, both closed in ledger #411:

1. The case table showed the flat list of reported levels
   ("BLOCKER, MAJOR") for a contract the matrix reports as BLOCKER
   (the matrix takes the strongest finding for a contract -
   agent/matrix_policy.py: _court_sort_key). The record already carried
   the contract's level (ledger #406), but the REPORT did not show it,
   so the two artifacts disagreed about the same case - and the report
   is the one a human reads.

2. The report carried the "Severity Agreement" percentage but not the
   drift itself: not which cases drifted, not what the tool said, and
   not which evidence produced the level it chose. The console summary
   said all of that; the shared artifact did not. A number nobody can
   act on is half a report.
"""

from __future__ import annotations

from evidence.report import render_eval_report


def _finding(severity: str, evidence_type: str = "java_source_diff") -> dict:
    return {
        "contract_id": "COURT-01",
        "severity": severity,
        "evidence_type": evidence_type,
        "id": "f-1",
    }


def _record(**overrides) -> dict:
    record = {
        "case": "case-01",
        "verdict": "PASS",
        "should_detect": True,
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 1,
        "matched_severities": "MAJOR",
        "contracts_found": "COURT-01",
        "severity_match": True,
        "finding_evidence": [_finding("MAJOR")],
    }
    record.update(overrides)
    return record


def _row_for(html: str, case: str) -> str:
    body = html.split("<tbody>")[1].split("</tr>")
    for row in body:
        if case in row:
            return row
    raise AssertionError(f"no row for {case}")


def test_the_table_shows_the_contract_level_not_the_flat_list() -> None:
    """One contract, one level: the matrix's rule (the strongest finding
    for that contract) - and the report must not disagree with it."""
    html = render_eval_report(
        [
            _record(
                case="case-22",
                matched_severities="BLOCKER, MAJOR",
                contract_level="BLOCKER",
                all_matched_severities="BLOCKER, MAJOR",
            )
        ],
        None,
    )
    row = _row_for(html, "case-22")
    assert ">BLOCKER<" in row, row
    assert "also reported: BLOCKER, MAJOR" in row, (
        "the full list must stay visible - nothing is dropped"
    )


def test_a_report_without_the_new_field_still_shows_the_levels() -> None:
    """An older record has no contract_level; the report must still say
    something true."""
    html = render_eval_report(
        [_record(case="case-old", matched_severities="MAJOR")],
        None,
    )
    row = _row_for(html, "case-old")
    assert ">MAJOR<" in row, row


def test_the_drift_is_listed_with_the_evidence_that_caused_it() -> None:
    """The agreement number says HOW MUCH; this says WHICH and WHY."""
    html = render_eval_report(
        [
            _record(
                case="case-17",
                expected_severity="BLOCKER",
                matched_severities="MAJOR",
                contract_level="MAJOR",
                all_matched_severities="MAJOR",
                severity_match=False,
                finding_evidence=[
                    _finding("MAJOR", "base_pass_head_fail"),
                ],
            )
        ],
        None,
    )
    assert "Severity drift" in html
    assert "case-17" in html
    assert "expected BLOCKER" in html, html
    assert "got MAJOR" in html, html
    assert "base_pass_head_fail" in html, "the evidence is named"


def test_a_run_without_drift_has_no_drift_section() -> None:
    html = render_eval_report([_record()], None)
    assert "Severity drift" not in html
