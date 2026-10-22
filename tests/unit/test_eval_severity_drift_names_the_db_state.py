"""The drift list must name the thing that actually decides the level.

The report (and the console) explained a severity drift with the
finding's EVIDENCE KIND. On the real run that explains nothing: every
drift case had the same kind (``base_pass_head_fail``).

What actually decides the level is the DB STATE the evidence path
observed. Measured on the real run (ledger #418):

    DB_MUTATED / DB_MUTATED_ON_UNAUTH  => BLOCKER
    DB_CONSISTENT / no DB observation  => MAJOR

with no exceptions. So the drift is not the tool guessing - it is the
tool applying a rule, and the pool's expectation disagreeing with it.
A reader can only see that if the page shows the DB state.

These tests are SHARP: removing the db state from the drift entry (or
from the page) makes them fail.
"""

from __future__ import annotations

from typing import Any

from evidence.acceptance import severity_reconciliation
from evidence.report import render_eval_report


def _finding(
    severity: str,
    *,
    contract_id: str = "UNIQUE-01",
    evidence_type: str = "base_pass_head_fail",
    db_state_verdict: str = "",
) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "severity": severity,
        "evidence_type": evidence_type,
        "db_state_verdict": db_state_verdict,
        "confidence": 0.9,
    }


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": "case-01",
        "verdict": "PASS",
        "should_detect": True,
        "expected_contract": "UNIQUE-01",
        "expected_severity": "BLOCKER",
        "expected_evidence": "differential_test",
        "matched_findings": 1,
        "matched_severities": "MAJOR",
        "contract_level": "MAJOR",
        "all_matched_severities": "MAJOR",
        "contracts_found": "UNIQUE-01",
        "finding_evidence": [_finding("MAJOR", db_state_verdict="DB_CONSISTENT")],
    }
    record.update(overrides)
    return record


def test_the_drift_entry_carries_the_db_state_the_level_came_from() -> None:
    rec = severity_reconciliation([_record()])
    drift = rec["mismatches"][0]
    assert drift["case"] == "case-01"
    assert drift["expected"] == "BLOCKER"
    assert drift["actual"] == "MAJOR"
    assert drift["db_state_verdicts"] == "DB_CONSISTENT"


def test_the_page_shows_the_db_state_next_to_the_drift() -> None:
    """Sharp: without the db state the page says only "base_pass_head_fail",
    which is the same string for every drift case."""
    html = render_eval_report([_record()], None)
    assert "Severity drift" in html
    assert "DB_CONSISTENT" in html, html[-3000:]
    assert "db state" in html


def test_a_drift_with_no_db_observation_still_renders() -> None:
    record = _record(
        finding_evidence=[_finding("MAJOR", db_state_verdict="")],
    )
    rec = severity_reconciliation([record])
    assert rec["mismatches"][0]["db_state_verdicts"] == ""
    html = render_eval_report([record], None)
    assert "Severity drift" in html
    assert "db state" not in html


def test_the_drift_entry_keeps_the_evidence_kind_too() -> None:
    """The db state is ADDED, not a replacement: the kind is still a fact
    about how the case was compared."""
    rec = severity_reconciliation([_record()])
    drift = rec["mismatches"][0]
    assert drift["evidence_kinds"] == "base_pass_head_fail"
    assert drift["db_state_verdicts"] == "DB_CONSISTENT"


def test_the_rule_the_db_state_implies_is_the_rule_the_tool_applies() -> None:
    """The measurement, pinned as a test.

    Two cases with the same evidence kind and DIFFERENT db states get
    DIFFERENT levels - that is what makes the db state the deciding
    thing, and it is what the page now shows.
    """
    consistent = _record(
        case="case-consistent",
        finding_evidence=[_finding("MAJOR", db_state_verdict="DB_CONSISTENT")],
    )
    mutated = _record(
        case="case-mutated",
        expected_severity="MAJOR",
        matched_severities="BLOCKER",
        contract_level="BLOCKER",
        all_matched_severities="BLOCKER",
        finding_evidence=[
            _finding("BLOCKER", db_state_verdict="DB_MUTATED_ON_UNAUTH")
        ],
    )
    rec = severity_reconciliation([consistent, mutated])
    by_case = {m["case"]: m for m in rec["mismatches"]}
    assert by_case["case-consistent"]["db_state_verdicts"] == "DB_CONSISTENT"
    assert by_case["case-mutated"]["db_state_verdicts"] == "DB_MUTATED_ON_UNAUTH"
    # both have the SAME evidence kind, and the levels differ
    assert by_case["case-consistent"]["evidence_kinds"] == (
        by_case["case-mutated"]["evidence_kinds"]
    )
    assert by_case["case-consistent"]["actual"] == "MAJOR"
    assert by_case["case-mutated"]["actual"] == "BLOCKER"


def test_the_db_state_shown_is_the_one_that_produced_the_level() -> None:
    """The explanation must come from the SAME findings as the level.

    A case whose expected contract was never found is answered by
    evidence type alone, and the finding that answered it belongs to a
    DIFFERENT contract. The page must not show a DB state from a finding
    that did not produce the level (ledger #418).
    """
    record = _record(
        case="case-other-contract",
        expected_contract="BOUNDARY-01",     # the case is about this one
        expected_severity="BLOCKER",
        matched_severities="MAJOR",
        contract_level="MAJOR",
        all_matched_severities="MAJOR",
        finding_evidence=[
            # the finding that answered the case, for ANOTHER contract
            _finding("MAJOR", contract_id="AUTH-01",
                     db_state_verdict="DB_NO_EVIDENCE"),
        ],
    )
    rec = severity_reconciliation([record])
    drift = rec["mismatches"][0]
    # the level came from the AUTH-01 finding (the only one), so the db
    # state shown must be that finding's - not some other contract's
    assert drift["actual"] == "MAJOR"
    assert drift["db_state_verdicts"] == "DB_NO_EVIDENCE"


def test_the_db_state_comes_from_the_cases_own_findings() -> None:
    """When the case's own contract HAS findings, only those count."""
    record = _record(
        expected_contract="UNIQUE-01",
        finding_evidence=[
            _finding("MAJOR", contract_id="UNIQUE-01",
                     db_state_verdict="DB_CONSISTENT"),
            # another contract's finding, with a different db state
            _finding("BLOCKER", contract_id="CACHE-01",
                     db_state_verdict="DB_MUTATED_ON_UNAUTH"),
        ],
    )
    rec = severity_reconciliation([record])
    drift = rec["mismatches"][0]
    assert drift["db_state_verdicts"] == "DB_CONSISTENT"


def test_own_findings_is_the_source_the_level_is_read_from() -> None:
    from evidence.acceptance import own_findings

    record = _record(
        expected_contract="UNIQUE-01",
        finding_evidence=[
            _finding("MAJOR", contract_id="UNIQUE-01"),
            _finding("BLOCKER", contract_id="CACHE-01"),
        ],
    )
    own = own_findings(record)
    assert [f["contract_id"] for f in own] == ["UNIQUE-01"]
    # the level and the db state read the SAME findings
    from evidence.acceptance import severity_levels_of

    assert severity_levels_of(record) == [str(f["severity"]) for f in own]
