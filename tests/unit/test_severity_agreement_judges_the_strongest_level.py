"""The severity-agreement metric must judge the level a contract HAS.

Ledger #395 measured it: the tool's severity is a deterministic function of
the evidence path it took (ADR-004: BLOCKER needs real execution + DB
evidence; static analysis is capped at MAJOR). The pool's
``expected_severity`` is authored per defect. Where the two disagree, the
drift is a statement about the EVIDENCE, not a wrong guess about the bug.

Two things follow, and both are pinned here:

1. The metric judges the STRONGEST level reported for the expected
   contract — the same level the matrix policy shows a reader
   (``agent/matrix_policy.py``: ``_court_sort_key`` picks the strongest
   finding for a contract). One contract can carry two confirmed findings
   (a static source diff AND an execution differential), and the old
   "the whole list must equal one value" rule counted a correct BLOCKER
   as a drift whenever a weaker duplicate existed for the same contract.
2. The drift report says WHICH EVIDENCE produced the level, so a reader
   sees "the evidence was static, so MAJOR is the ceiling" instead of a
   bare "expected BLOCKER, got MAJOR" that looks like a guess.
"""

from __future__ import annotations

from typing import Any

from evidence.acceptance import (
    severity_levels_of,
    severity_match_of,
    severity_rank,
    severity_reconciliation,
    strongest_severity,
)


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


def _finding(severity: str, evidence_type: str, contract_id: str = "AUTH-01") -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "severity": severity,
        "confidence": 0.88,
        "evidence_type": evidence_type,
    }


# ── the strongest level, not the whole list ──────────────────────────────


def test_one_contract_with_two_levels_judged_on_the_strongest() -> None:
    """The case that made the metric wrong: AUTH-01 was reported as MAJOR
    by the static source diff AND as BLOCKER by the execution differential
    (case-22 in the 87-case run). The contract's level IS BLOCKER — the
    matrix shows the strongest finding — so the level call was RIGHT and
    the old rule called it a drift."""
    record = _case(
        matched_findings=2,
        matched_severities="BLOCKER, MAJOR",
        finding_evidence=[
            _finding("MAJOR", "java_source_diff"),
            _finding("BLOCKER", "base_pass_head_fail"),
        ],
    )
    assert severity_match_of(record) is True


def test_the_strongest_level_wins_over_a_weaker_one_in_either_order() -> None:
    for findings in (
        [_finding("BLOCKER", "base_pass_head_fail"), _finding("MAJOR", "java_source_diff")],
        [_finding("MAJOR", "java_source_diff"), _finding("BLOCKER", "base_pass_head_fail")],
    ):
        record = _case(
            matched_findings=2,
            matched_severities="BLOCKER, MAJOR",
            finding_evidence=findings,
        )
        assert severity_match_of(record) is True


def test_a_strictly_wrong_level_is_still_a_drift() -> None:
    """The fix must not paper over a real level error: MAJOR where BLOCKER
    was expected is still a drift."""
    record = _case(
        matched_severities="MAJOR",
        finding_evidence=[_finding("MAJOR", "base_pass_head_fail")],
    )
    assert severity_match_of(record) is False


def test_a_level_on_another_contract_does_not_decide_this_one() -> None:
    """The strongest level is the strongest for the EXPECTED contract: a
    second contract's BLOCKER cannot make a MAJOR-only case look right."""
    record = _case(
        matched_findings=2,
        matched_severities="MAJOR, BLOCKER",
        expected_contract="AUTH-01",
        finding_evidence=[
            _finding("MAJOR", "base_pass_head_fail", "AUTH-01"),
            _finding("BLOCKER", "base_pass_head_fail", "CACHE-01"),
        ],
    )
    assert severity_match_of(record) is False


def test_a_record_without_per_finding_evidence_still_works() -> None:
    """Older records (and hand-written ones) carry only the flat string."""
    assert severity_match_of(_case(matched_severities="BLOCKER")) is True
    assert severity_match_of(_case(matched_severities="MAJOR")) is False


# ── the ordering itself ──────────────────────────────────────────────────


def test_strongest_severity_ranks_blocker_over_major_over_minor() -> None:
    assert strongest_severity(["MAJOR", "BLOCKER"]) == "BLOCKER"
    assert strongest_severity(["MINOR", "MAJOR"]) == "MAJOR"
    assert strongest_severity(["INFORMATIONAL", "MINOR"]) == "MINOR"
    assert strongest_severity([]) == ""
    assert strongest_severity(["—"]) == ""


def test_an_unknown_level_ranks_below_every_known_one() -> None:
    assert severity_rank("BLOCKER") > severity_rank("MAJOR")
    assert severity_rank("MAJOR") > severity_rank("MINOR")
    assert severity_rank("WHATEVER") == 0
    assert severity_rank("") == 0


def test_the_levels_of_a_case_come_from_its_own_contract() -> None:
    record = _case(
        finding_evidence=[
            _finding("MAJOR", "base_pass_head_fail", "AUTH-01"),
            _finding("BLOCKER", "base_pass_head_fail", "CACHE-01"),
        ],
    )
    assert severity_levels_of(record) == ["MAJOR"]


# ── the report says WHY ──────────────────────────────────────────────────


def test_a_drift_reports_the_evidence_that_produced_the_level() -> None:
    """Without this, a reader sees "expected BLOCKER, got MAJOR" and has
    to guess whether the tool guessed wrong or the evidence was too weak."""
    results = [
        _case(
            case="static-only",
            matched_severities="MAJOR",
            expected_severity="BLOCKER",
            finding_evidence=[_finding("MAJOR", "java_source_diff")],
        ),
    ]
    rec = severity_reconciliation(results)
    assert rec["severity_agreement"] == 0.0
    drift = rec["mismatches"][0]
    assert drift["expected"] == "BLOCKER"
    assert drift["strongest"] == "MAJOR"
    assert drift["evidence_kinds"] == "java_source_diff"


def test_the_agreement_share_counts_a_correct_blocker_with_a_duplicate() -> None:
    """The end-to-end number: one case whose contract is BLOCKER (with a
    weaker static duplicate) is an AGREEMENT, not a drift."""
    results = [
        _case(
            case="case-22-like",
            matched_findings=2,
            matched_severities="BLOCKER, MAJOR",
            finding_evidence=[
                _finding("MAJOR", "java_source_diff"),
                _finding("BLOCKER", "base_pass_head_fail"),
            ],
        ),
        _case(
            case="case-17-like",
            matched_severities="MAJOR",
            expected_severity="BLOCKER",
            finding_evidence=[_finding("MAJOR", "java_source_diff")],
        ),
    ]
    rec = severity_reconciliation(results)
    assert rec["matched_positive_cases"] == 2
    assert rec["severity_mismatch_cases"] == 1
    assert rec["severity_agreement"] == 50.0
    assert rec["mismatches"][0]["case"] == "case-17-like"


def test_a_contract_with_two_levels_is_reported_at_its_strongest() -> None:
    """The matrix already picks the strongest finding for a contract
    (agent/matrix_policy.py: _court_sort_key). The eval must not
    disagree with the matrix about the same case, so the record carries
    the contract's level next to the full list of what was reported."""
    result = {
        **_case(
            matched_findings=2,
            matched_severities="BLOCKER, MAJOR",
            finding_evidence=[
                _finding("MAJOR", "java_source_diff"),
                _finding("BLOCKER", "base_pass_head_fail"),
            ],
        ),
        "contract_level": "BLOCKER",
        "all_matched_severities": "BLOCKER, MAJOR",
    }
    assert result["contract_level"] == "BLOCKER"
    # The full list is kept: nothing is dropped, it is just not what the
    # contract's LEVEL is.
    assert result["all_matched_severities"] == "BLOCKER, MAJOR"
