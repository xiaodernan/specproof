"""#258 — the Review Court must see the in-flight evidence run_differential emits.

run_differential emits three runtime-evidence fields on every differential
record (#250 behavioral_evidence, #253/#254 db_violation_evidence, and the
human-readable db_state_detail). Until #258 these fields were part of the
emitted record but were NOT copied into the court candidate, so they were
silently dropped before reaching confirmed_findings and the report — making
#250/#254 capture invisible downstream.

These tests pin that the fields survive end-to-end. They are capture-only:
none of them change severity/confidence or the ADR-004 gate; they only make
the already-captured signal visible to the court and report.

All inputs are offline fakes — no workspaces, no LLM, no git.
"""
from typing import Any, cast

from agent.nodes.review_court import _build_candidates, run_review_court
from agent.state import Phase0State

APPROVED_AUTH: dict[str, Any] = {"id": "AUTH-01", "approved": True}
GENERATED_TESTS: str = "capsules/tests/AuthFlowTest.java"

_BEHAVIORAL = {
    "captured": True,
    "head_test_failed": True,
    "db_effect_rolled_back": False,
    "failing_method": "changeEmail_duplicateRejected",
    "note": "Behavioral regression with captured DB mutation.",
}
_DB_VIOLATION = {
    "marker": "DB STATE VIOLATION",
    "head_observed": True,
    "base_observed": False,
    "head_only": True,
}


def _regression_record(**overrides: Any) -> dict[str, Any]:
    """A differential record that carries the full runtime-evidence set."""
    record: dict[str, Any] = {
        "contract_id": "AUTH-01",
        "verdict": "REGRESSION",
        "detail": "duplicate-email change accepted and persisted",
        "severity": "BLOCKER",
        "confidence": 0.95,
        "evidence_type": "base_pass_head_fail",
        "base_exit_code": 0,
        "head_exit_code": 1,
        "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
        "db_state_detail": "Head persisted a duplicate email; base did not.",
        "behavioral_evidence": dict(_BEHAVIORAL),
        "db_violation_evidence": dict(_DB_VIOLATION),
        "location": "src/AuthController.java",
        "evidence_digest": "",
    }
    record.update(overrides)
    return record


class TestBuildCandidatesPropagatesInflightEvidence:
    """_build_candidates must copy the runtime-evidence fields verbatim."""

    def test_three_fields_copied_for_regression(self) -> None:
        state: dict[str, Any] = {
            "static_findings": [],
            "diff_results": [_regression_record()],
        }
        candidates = _build_candidates(cast(Phase0State, state))
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand["db_state_detail"] == "Head persisted a duplicate email; base did not."
        assert cand["behavioral_evidence"] == _BEHAVIORAL
        assert cand["db_violation_evidence"] == _DB_VIOLATION

    def test_db_violation_head_only_flag_survives(self) -> None:
        state: dict[str, Any] = {
            "static_findings": [],
            "diff_results": [_regression_record()],
        }
        cand = _build_candidates(cast(Phase0State, state))[0]
        # The case-17 shape: the generated test observed the DB-state violation
        # on head only — this is the exact signal #254 captures.
        assert cand["db_violation_evidence"]["head_only"] is True
        assert cand["db_violation_evidence"]["head_observed"] is True
        assert cand["db_violation_evidence"]["base_observed"] is False

    def test_absent_fields_default_to_empty_dict(self) -> None:
        bare = _regression_record()
        del bare["behavioral_evidence"]
        del bare["db_violation_evidence"]
        del bare["db_state_detail"]
        state: dict[str, Any] = {
            "static_findings": [],
            "diff_results": [bare],
        }
        cand = _build_candidates(cast(Phase0State, state))[0]
        assert cand["behavioral_evidence"] == {}
        assert cand["db_violation_evidence"] == {}
        assert cand["db_state_detail"] == ""


class TestCourtNodeSurfaceInflightEvidence:
    """run_review_court must carry the fields into confirmed_findings."""

    def test_fields_reach_confirmed_findings(self) -> None:
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [],
            "diff_results": [_regression_record()],
            "contracts": [APPROVED_AUTH],
            "generated_tests_path": GENERATED_TESTS,
        }
        result = run_review_court(cast(Phase0State, state))
        assert len(result["confirmed_findings"]) == 1
        confirmed = result["confirmed_findings"][0]
        assert confirmed["db_state_detail"] == "Head persisted a duplicate email; base did not."
        assert confirmed["behavioral_evidence"] == _BEHAVIORAL
        assert confirmed["db_violation_evidence"] == _DB_VIOLATION

    def test_fields_also_reach_court_audit(self) -> None:
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [],
            "diff_results": [_regression_record()],
            "contracts": [APPROVED_AUTH],
            "generated_tests_path": GENERATED_TESTS,
        }
        result = run_review_court(cast(Phase0State, state))
        audit = result["court_audit"][0]
        assert audit["db_violation_evidence"] == _DB_VIOLATION
        assert audit["behavioral_evidence"] == _BEHAVIORAL
        assert audit["db_state_detail"] == "Head persisted a duplicate email; base did not."
