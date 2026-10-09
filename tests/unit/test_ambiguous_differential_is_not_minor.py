"""Gate: a confirmed head-only regression must not come out MINOR (#222).

The end-to-end eval (4-case CI subset, 2026-10-09) finally ran the
differential for real and produced the first clean reading of the product:

    Recall 66.7%   Severity agreement 0.0%   Severe precision 0.0%
      ! severity drift: case-21 expected BLOCKER, got MINOR
      ! severity drift: case-56 expected MAJOR,   got MINOR

Both detected positives were CONFIRMED findings graded MINOR — so the §14 SLO
"BLOCKER/MAJOR Precision >= 90%" read 0% on the only sample that measures it.

Root cause: the split differential emits its both-sides-fail entries WITHOUT a
severity (deliberately — see ``run_differential``'s split path — so the court
compares the failure signatures), and ``_build_candidates`` then filled that
gap with ``"MAJOR" if verdict == "REGRESSION" else "MINOR"``. The AMBIGUOUS
branch is the one that carries the *stronger* evidence (a base/head signature
comparison), yet it got the weaker default — below plain static analysis,
which defaults to MAJOR. When the comparison proves a head-only difference the
policy confirms the finding and keeps that placeholder as the final grade.

These are pure-function assertions: no pipeline, no Docker, no model.
"""

from __future__ import annotations

from typing import Any

from agent.nodes.review_court import _build_candidates
from agent.review_court.policy import (
    NOT_ATTRIBUTED_SEVERITY,
    policy_recalculate,
)


def _split_record(**overrides: Any) -> dict[str, Any]:
    """A split-differential both-sides-fail record: no severity, AMBIGUOUS."""
    record: dict[str, Any] = {
        "contract_id": "AUTH-01",
        "verdict": "AMBIGUOUS",
        "evidence_type": "differential_execution",
        "severity": None,
        "confidence": 0.65,
        "detail": "both sides fail — signatures compared by the Review Court",
        "base_exit_code": 1,
        "head_exit_code": 1,
        "base_output": "java.lang.AssertionError: expected:<denied> but was:<allowed>",
        "head_output": "java.lang.AssertionError: expected:<401> but was:<200>",
        "base_test_counts": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
        "head_test_counts": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
    }
    record.update(overrides)
    return record


def _state(diff_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"static_findings": [], "diff_results": diff_results}


def test_ambiguous_without_a_severity_is_graded_major_not_minor() -> None:
    candidates = _build_candidates(_state([_split_record()]))

    assert len(candidates) == 1, candidates
    assert candidates[0]["severity"] == "MAJOR", (
        "an AMBIGUOUS split record has no severity of its own; the court "
        "fills the gap, and it must not fill it with a grade below the "
        "static-evidence default"
    )


def test_a_clean_regression_without_a_severity_is_also_major() -> None:
    """Negative control: the REGRESSION branch is unchanged."""
    candidates = _build_candidates(_state([_split_record(verdict="REGRESSION")]))
    assert [c["severity"] for c in candidates] == ["MAJOR"]


def test_none_severity_entries_stay_bookkeeping() -> None:
    """The explicit "NONE" value is a different thing and must stay skipped."""
    assert _build_candidates(_state([_split_record(severity="NONE")])) == []


def test_the_confirmed_grade_survives_the_court() -> None:
    """End of the chain: the confirmed finding must not read MINOR.

    The split record's signatures differ (denied/allowed vs 401/200), so the
    preexisting rule finds a head-only difference and confirms the finding —
    and the grade it carries out is the placeholder from _build_candidates.
    """
    record = _split_record()
    candidates = _build_candidates(_state([record]))
    result = policy_recalculate(candidates, diff_results=[record])

    audit = result["audit_entries"][0]
    assert audit["preexisting_check"]["head_only_difference"] is True
    assert audit["final_status"] == "confirmed"
    assert audit["final_severity"] != "MINOR", (
        f"a confirmed head-introduced regression was graded "
        f"{audit['final_severity']!r} — it would not block anything"
    )
    assert result["confirmed_findings"][0]["severity"] != "MINOR"


def test_identical_signatures_are_still_not_attributed() -> None:
    """The pre-existing-defect rule is untouched by this change.

    Same failure on both sides means the defect was already there: the grade
    the candidate carries must not leak into the verdict.
    """
    same = "java.lang.AssertionError: expected:<denied> but was:<allowed>"
    record = _split_record(base_output=same, head_output=same)
    candidates = _build_candidates(_state([record]))
    result = policy_recalculate(candidates, diff_results=[record])

    audit = result["audit_entries"][0]
    assert audit["preexisting_check"]["head_only_difference"] is False
    assert audit["final_severity"] == NOT_ATTRIBUTED_SEVERITY
