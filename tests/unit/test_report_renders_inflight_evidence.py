"""#261 — the HTML Verification Report must surface the in-flight evidence.

run_differential emits behavioral_evidence / db_violation_evidence /
db_state_detail on each confirmed finding (#250/#253/#254). #261 makes them
reach confirmed_findings and the court_audit; this test pins that they ALSO
appear in the user-facing HTML report, so the verdict is explainable rather
than merely asserted.

Offline: render_verification_report is a pure function of its args.
"""
from evidence.report import render_verification_report

_DB_VIOLATION = {
    "marker": "DB STATE VIOLATION",
    "head_observed": True,
    "base_observed": False,
    "head_only": True,
}
_BEHAVIORAL = {
    "captured": True,
    "head_test_failed": True,
    "db_effect_rolled_back": False,
    "failing_method": "changeEmail",
    "note": "Behavioral regression with captured DB mutation.",
}


def _finding(**overrides: object) -> dict:
    f = {
        "severity": "BLOCKER",
        "contract_id": "AUTH-01",
        "description": "duplicate email accepted and persisted",
        "confidence": 0.95,
        "evidence_type": "base_pass_head_fail",
        "db_state_detail": "Head persisted a duplicate email; base did not.",
        "behavioral_evidence": dict(_BEHAVIORAL),
        "db_violation_evidence": dict(_DB_VIOLATION),
    }
    f.update(overrides)
    return f


def _render(finding: dict) -> str:
    return render_verification_report(
        "repo", "base", "head", {}, [finding],
        generated_at="2026-10-14 00:00:00 UTC",
    )


class TestReportRendersInflightEvidence:
    def test_db_state_detail_shown(self) -> None:
        assert "DB state: Head persisted a duplicate email; base did not." in _render(_finding())

    def test_in_flight_db_violation_marker_shown(self) -> None:
        html = _render(_finding())
        assert "DB STATE VIOLATION" in html
        assert "head-only: True" in html

    def test_behavioral_capture_note_shown(self) -> None:
        html = _render(_finding())
        assert "Behavioral regression captured in-flight:" in html
        assert "Behavioral regression with captured DB mutation." in html

    def test_evidence_omitted_when_absent(self) -> None:
        plain = _finding()
        del plain["db_state_detail"]
        del plain["behavioral_evidence"]
        del plain["db_violation_evidence"]
        html = _render(plain)
        assert "DB STATE VIOLATION" not in html
        assert "Behavioral regression captured in-flight:" not in html
        assert "DB state:" not in html
