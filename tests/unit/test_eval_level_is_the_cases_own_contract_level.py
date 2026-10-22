"""The report's table cell and the report's drift line must say the SAME
thing about the same case.

Ledger #406 made the eval record carry the contract's level next to the
flat list of what was reported, and #411 put that level in the report's
table cell. #413 found the two artifacts STILL disagreed - and the
disagreement was in the code, waiting for the first case that triggered
it:

- ``contract_level`` was the strongest level over EVERY finding that
  answered the case;
- the severity judgement was the strongest level over the findings that
  carry the case's OWN contract id.

A finding can answer a case by naming the expected evidence even when it
belongs to a DIFFERENT contract (``matched_findings`` matches on
evidence type OR contract id). When such a finding carried the stronger
level, the page said BLOCKER in the table and MINOR in the drift line -
about the same case, on the same page.

The fix puts the rule in ONE place (``evidence.acceptance.contract_levels``)
and uses it for both. These tests are SHARP: reverting the fix makes them
fail.
"""

from __future__ import annotations

import re
from typing import Any

from cli.specproof.commands.eval import (
    case_contract_level,
    matched_findings,
)
from evidence.acceptance import (
    contract_levels,
    severity_levels_of,
    strongest_severity,
)
from evidence.report import render_eval_report


def _finding(
    severity: str,
    contract_id: str = "COURT-01",
    evidence_type: str = "base_pass_head_fail",
) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "severity": severity,
        "evidence_type": evidence_type,
        "id": f"f-{contract_id}-{severity}",
    }


#: A case whose findings answer it by EVIDENCE, one of them belonging to a
#: different contract - the shape that made the two artifacts disagree.
TWO_CONTRACT_FINDINGS = [
    _finding("MINOR", "COURT-01", "java_source_diff"),
    _finding("BLOCKER", "CACHE-01", "base_pass_head_fail"),
]


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": "case-01",
        "verdict": "PASS",
        "should_detect": True,
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 2,
        "matched_severities": "BLOCKER, MINOR",
        "contracts_found": "COURT-01, CACHE-01",
        "finding_evidence": list(TWO_CONTRACT_FINDINGS),
    }
    record.update(overrides)
    return record


# -- the rule itself -------------------------------------------------------


def test_the_level_comes_from_the_cases_own_contract() -> None:
    """Another contract's finding does not decide this case's level."""
    assert contract_levels(TWO_CONTRACT_FINDINGS, "COURT-01") == ["MINOR"]
    assert strongest_severity(contract_levels(TWO_CONTRACT_FINDINGS, "COURT-01")) == "MINOR"


def test_when_no_finding_carries_the_contract_the_answering_ones_decide() -> None:
    """A case matched only by evidence type: those findings are its levels."""
    findings = [_finding("BLOCKER", "CACHE-01", "base_pass_head_fail")]
    assert contract_levels(findings, "COURT-01") == ["BLOCKER"]


def test_a_case_without_a_contract_uses_every_level() -> None:
    findings = [_finding("MAJOR", "COURT-01"), _finding("MINOR", "CACHE-01")]
    assert contract_levels(findings, "") == ["MAJOR", "MINOR"]


def test_a_non_dict_finding_is_not_a_level() -> None:
    assert contract_levels([_finding("MAJOR"), "not-a-dict"], "COURT-01") == ["MAJOR"]


# -- the level the record actually carries ----------------------------------


def test_the_record_carries_the_cases_own_contract_level() -> None:
    """THE regression test: the record's level, computed by the real code.

    Sharp: with the #411 computation (the strongest over every finding
    that answered the case) this record carried BLOCKER - another
    contract's level - and the page said BLOCKER in the table and MINOR
    in the drift line, about the same case.
    """
    matched = matched_findings(
        TWO_CONTRACT_FINDINGS, "COURT-01", "base_pass_head_fail"
    )
    assert len(matched) == 2, "both findings answer the case (one by evidence)"
    assert case_contract_level(matched, "COURT-01") == "MINOR"


def test_a_case_matched_only_by_the_contract_id_keeps_its_level() -> None:
    matched = matched_findings(
        [_finding("BLOCKER", "COURT-01")], "COURT-01", "no-such-evidence"
    )
    assert case_contract_level(matched, "COURT-01") == "BLOCKER"


def test_a_case_with_nothing_matched_has_no_level() -> None:
    assert case_contract_level([], "COURT-01") == ""


# -- the two artifacts must agree -------------------------------------------


def test_the_table_cell_and_the_drift_line_say_the_same_thing() -> None:
    """The bug, end to end: the page said BLOCKER in the table, MINOR in
    the drift - about the same case, on the same page."""
    matched = matched_findings(
        TWO_CONTRACT_FINDINGS, "COURT-01", "base_pass_head_fail"
    )
    record = _record(
        contract_level=case_contract_level(matched, "COURT-01"),
        all_matched_severities="BLOCKER, MINOR",
    )
    html = render_eval_report([record], None)

    row = re.search(r"<tr>\s*<td>case-01.*?</tr>", html, re.S)
    assert row is not None
    cell = re.findall(r"<td[^>]*>(.*?)</td>", row.group(), re.S)
    assert "MINOR" in cell[6], cell
    assert "BLOCKER<" not in cell[6], (
        "another contract's level must not be shown as this case's level"
    )

    drift = re.search(r"<li><b>case-01</b>.*?</li>", html, re.S)
    assert drift is not None
    assert "got MINOR" in drift.group(), drift.group()


def test_the_record_level_and_the_judged_level_are_the_same_value() -> None:
    """The record and the judgement read the same level off the record."""
    matched = matched_findings(
        TWO_CONTRACT_FINDINGS, "COURT-01", "base_pass_head_fail"
    )
    record = _record(
        contract_level=case_contract_level(matched, "COURT-01"),
    )
    judged = strongest_severity(severity_levels_of(record))
    assert record["contract_level"] == judged


def test_the_two_rules_agree_on_every_shape_of_case() -> None:
    """The record-based rule and the findings-based rule are the same rule.

    Without this they drift apart again the moment a new shape of case
    shows up - which is exactly how #413 happened.
    """
    shapes = [
        # (findings that answered the case, expected contract)
        ([], "COURT-01"),
        ([_finding("MAJOR", "COURT-01")], "COURT-01"),
        ([_finding("MAJOR", "CACHE-01")], "COURT-01"),
        (
            [_finding("MINOR", "COURT-01"), _finding("BLOCKER", "CACHE-01")],
            "COURT-01",
        ),
        ([_finding("BLOCKER", "CACHE-01")], ""),
    ]
    for findings, contract in shapes:
        record = {
            "expected_contract": contract,
            "matched_severities": ", ".join(
                sorted({str(f["severity"]) for f in findings})
            ),
            "finding_evidence": findings,
        }
        from_findings = case_contract_level(findings, contract)
        from_record = strongest_severity(severity_levels_of(record))
        assert from_findings == from_record, (findings, contract)
