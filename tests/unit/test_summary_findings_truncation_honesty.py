"""#264 — the job summary must not masquerade truncated findings for the whole set.

`_state_summary` carries at most SUMMARY_FINDINGS_CAP findings, but before #264
it exposed only the capped list with no total and no truncation flag. A consumer
(e.g. a dashboard rendering ``len(summary["findings"])`` as "findings total")
would report a job with 40 confirmed findings as having 20 — silent
under-reporting, the same class the DEEP-disclosure (#155) and matrix_rows
(#147) rules forbid.

These tests lock the honest projection: ``findings_total`` is the authoritative
count and ``findings_truncated`` says whether the shown list is whole, so
"findings" reads as "showing N of M".

Prediction (before running): >cap findings -> list capped at CAP, total = real
count, truncated True; <=cap -> truncated False; empty -> all zero/false.

Offline: _state_summary is a pure function of its args.
"""
from agent.worker import (
    SUMMARY_CAPSULES_CAP,
    SUMMARY_ERRORS_CAP,
    SUMMARY_FINDINGS_CAP,
    _state_summary,
)


def _finding(i: int) -> dict:
    return {
        "id": f"COURT-AUTH-{i:02d}",
        "contract_id": "AUTH-01",
        "severity": "BLOCKER" if i % 2 == 0 else "MAJOR",
        "confidence": 0.95,
        "evidence_type": "base_pass_head_fail",
        "type": "differential_regression",
        "location": "src/AuthController.java",
        "description": f"finding {i}",
    }


def _summary(n: int) -> dict:
    state = {
        "matrix": {},
        "contracts": [],
        "confirmed_findings": [_finding(i) for i in range(n)],
        "errors": [],
    }
    return _state_summary(state, "BLOCKED")


class TestFindingsTruncationIsHonest:
    def test_over_cap_reports_total_and_flags_truncation(self) -> None:
        summary = _summary(SUMMARY_FINDINGS_CAP + 5)
        assert len(summary["findings"]) == SUMMARY_FINDINGS_CAP
        assert summary["findings_total"] == SUMMARY_FINDINGS_CAP + 5
        assert summary["findings_truncated"] is True

    def test_under_cap_is_not_flagged_truncated(self) -> None:
        summary = _summary(3)
        assert len(summary["findings"]) == 3
        assert summary["findings_total"] == 3
        assert summary["findings_truncated"] is False

    def test_exactly_cap_is_not_flagged_truncated(self) -> None:
        summary = _summary(SUMMARY_FINDINGS_CAP)
        assert len(summary["findings"]) == SUMMARY_FINDINGS_CAP
        assert summary["findings_total"] == SUMMARY_FINDINGS_CAP
        assert summary["findings_truncated"] is False

    def test_empty_findings_are_honest_zeros(self) -> None:
        summary = _summary(0)
        assert summary["findings"] == []
        assert summary["findings_total"] == 0
        assert summary["findings_truncated"] is False


def _summary_aux(capsules: list, errors: list) -> dict:
    state = {
        "matrix": {},
        "contracts": [],
        "confirmed_findings": [],
        "capsules": list(capsules),
        "errors": list(errors),
    }
    return _state_summary(state, "FAILED")


class TestCapsulesTruncationIsHonest:
    """#265: the capsules list is capped, so its total + truncation are reported."""

    def test_over_cap_reports_total_and_flags_truncation(self) -> None:
        summary = _summary_aux([f"c{i}.zip" for i in range(SUMMARY_CAPSULES_CAP + 3)], [])
        assert len(summary["capsules"]) == SUMMARY_CAPSULES_CAP
        assert summary["capsules_total"] == SUMMARY_CAPSULES_CAP + 3
        assert summary["capsules_truncated"] is True

    def test_at_cap_is_not_flagged_truncated(self) -> None:
        summary = _summary_aux([f"c{i}.zip" for i in range(SUMMARY_CAPSULES_CAP)], [])
        assert summary["capsules_total"] == SUMMARY_CAPSULES_CAP
        assert summary["capsules_truncated"] is False


class TestErrorsTruncationIsHonest:
    """#265: the errors list is capped, so its total + truncation are reported."""

    def test_over_cap_reports_total_and_flags_truncation(self) -> None:
        summary = _summary_aux([], [f"err {i}" for i in range(SUMMARY_ERRORS_CAP + 4)])
        assert len(summary["errors"]) == SUMMARY_ERRORS_CAP
        assert summary["errors_total"] == SUMMARY_ERRORS_CAP + 4
        assert summary["errors_truncated"] is True

    def test_under_cap_is_not_flagged_truncated(self) -> None:
        summary = _summary_aux([], ["err a", "err b"])
        assert summary["errors"] == ["err a", "err b"]
        assert summary["errors_total"] == 2
        assert summary["errors_truncated"] is False
