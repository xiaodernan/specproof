"""Gate #5 invariant tests - "无证据的严重评论 = 0" (docs/eval/go-nogo.md).

Pins the Review Court code paths that make a BLOCKER publication impossible
without real Base/Head execution evidence:

- agent/review_court/policy.py _has_real_execution_evidence: a recorded
  base/head run must carry exit-code keys on a base_pass_head_fail record,
  or on a differential_execution record with verdict REGRESSION.
  Condition 2_base_head_execution of the six-condition BLOCKER check
  consumes exactly this gate, and policy_recalculate demotes every
  BLOCKER with unmet conditions to MAJOR with confidence <= 0.88.
- agent/nodes/review_court.py _build_candidates: static-evidence
  candidates (NON_BLOCKER_EVIDENCE_TYPES) are capped at MAJOR / 0.85
  before the policy layer runs.
- agent/nodes/run_static_checks.py: the static node caps emitted findings
  at MAJOR / _STATIC_CONFIDENCE_CEILING (0.85) and stamps a p0_5_note.

All inputs are offline fakes - no workspaces, no LLM, no git.
"""
from pathlib import Path
from typing import Any, cast

import pytest

import agent.nodes.run_static_checks as run_static_checks
from agent.nodes.review_court import run_review_court
from agent.review_court.policy import (
    BLOCKER_REQUIRED_EVIDENCE_TYPES,
    DOWNGRADED_BLOCKER_CONFIDENCE_CEILING,
    STATIC_CONFIDENCE_CEILING,
    _check_blocker_conditions,
    _has_real_execution_evidence,
    policy_recalculate,
)
from agent.state import Phase0State

APPROVED_AUTH: dict[str, Any] = {"id": "AUTH-01", "approved": True}
CHANGED_FILES: list[str] = ["src/AuthController.java"]
GENERATED_TESTS: str = "capsules/tests/AuthFlowTest.java"


def _blocker_candidate(**overrides: Any) -> dict[str, Any]:
    """A fully-evidenced BLOCKER candidate (positive control)."""
    candidate: dict[str, Any] = {
        "id": "COURT-AUTH-01",
        "contract_id": "AUTH-01",
        "severity": "BLOCKER",
        "type": "differential_regression",
        "description": "Test passes in Base (exit 0) but fails in Head (exit 1)",
        "evidence_type": "base_pass_head_fail",
        "confidence": 0.95,
        "source": "differential",
        "status": "candidate",
        "diff_verdict": "REGRESSION",
        "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
        "location": "src/AuthController.java",
        "evidence_digest": "",
        "diff_result_index": 0,
    }
    candidate.update(overrides)
    return candidate


def _real_regression_record() -> dict[str, Any]:
    """The raw differential record behind the positive control (real exit codes)."""
    return {
        "contract_id": "AUTH-01",
        "verdict": "REGRESSION",
        "detail": "Test passes in Base (exit 0) but fails in Head (exit 1)",
        "severity": "BLOCKER",
        "confidence": 0.95,
        "evidence_type": "base_pass_head_fail",
        "base_exit_code": 0,
        "head_exit_code": 1,
        "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
        "location": "src/AuthController.java",
        "evidence_digest": "",
    }


def _static_candidate() -> dict[str, Any]:
    return {
        "id": "STATIC-AUTH-01",
        "contract_id": "AUTH-01",
        "severity": "BLOCKER",
        "type": "annotation_removed",
        "description": "@PreAuthorize removed from controller method",
        "evidence_type": "static_analysis",
        "confidence": 0.99,
        "source": "static_analysis",
        "status": "candidate",
    }


class TestNoExecutionEvidenceNeverPublishesBlocker:
    """(a) No recorded base/head run -> the court demotes BLOCKER to MAJOR."""

    def test_static_only_finding_is_capped_at_major(self) -> None:
        result = policy_recalculate([_static_candidate()])
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "MAJOR"
        assert confirmed["confidence"] <= STATIC_CONFIDENCE_CEILING
        audit = result["audit_entries"][0]
        assert not audit["blocker_check"]["blocker_conditions"][
            "2_base_head_execution"
        ]

    def test_differential_regression_without_exit_codes_is_demoted(self) -> None:
        candidate = _blocker_candidate(evidence_type="differential_execution")
        record = {
            "contract_id": "AUTH-01",
            "verdict": "REGRESSION",
            "detail": "regression claimed without a recorded run",
            "severity": "BLOCKER",
            "confidence": 0.95,
            "evidence_type": "differential_execution",
            "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
        }
        result = policy_recalculate(
            [candidate],
            contracts=[APPROVED_AUTH],
            diff_results=[record],
            generated_tests_path=GENERATED_TESTS,
            changed_files=CHANGED_FILES,
        )
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "MAJOR"
        assert confirmed["confidence"] <= DOWNGRADED_BLOCKER_CONFIDENCE_CEILING
        audit = result["audit_entries"][0]
        assert not audit["blocker_check"]["all_blocker_conditions_met"]
        assert not audit["blocker_check"]["blocker_conditions"][
            "2_base_head_execution"
        ]

    def test_no_diff_results_refuse_blocker(self) -> None:
        result = policy_recalculate(
            [_blocker_candidate()],
            contracts=[APPROVED_AUTH],
            diff_results=[],
            generated_tests_path=GENERATED_TESTS,
            changed_files=CHANGED_FILES,
        )
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "MAJOR"
        assert not result["audit_entries"][0]["blocker_check"][
            "all_blocker_conditions_met"
        ]

    def test_court_node_demotes_no_evidence_findings(self) -> None:
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [{
                "id": "STATIC-AUTH-01",
                "contract_id": "AUTH-01",
                "severity": "BLOCKER",
                "type": "annotation_removed",
                "description": "@PreAuthorize removed from controller method",
                "confidence": 0.99,
            }],
            "diff_results": [{
                "contract_id": "DIFF-01",
                "verdict": "REGRESSION",
                "detail": "regression claimed without recorded exit codes",
                "severity": "BLOCKER",
                "confidence": 0.95,
                "evidence_type": "differential_execution",
                "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
            }],
            "contracts": [APPROVED_AUTH],
            "generated_tests_path": GENERATED_TESTS,
        }
        result = run_review_court(cast(Phase0State, state))
        assert len(result["confirmed_findings"]) == 2
        assert all(f["severity"] == "MAJOR" for f in result["confirmed_findings"])
        assert all(f["severity"] != "BLOCKER" for f in result["confirmed_findings"])
        by_id = {a["id"]: a for a in result["court_audit"]}
        assert by_id["COURT-DIFF-01"]["final_severity"] == "MAJOR"
        assert not by_id["COURT-DIFF-01"]["blocker_check"][
            "blocker_conditions"
        ]["2_base_head_execution"]
        assert all(a["final_severity"] != "BLOCKER" for a in result["court_audit"])


class TestBlockerEvidenceGate:
    """(b) The six-condition BLOCKER path requires real execution evidence."""

    @pytest.mark.parametrize(
        "records",
        [
            [],
            [{"evidence_type": "base_pass_head_fail", "verdict": "REGRESSION"}],
            [{"evidence_type": "differential_execution", "verdict": "REGRESSION"}],
            [{
                "evidence_type": "static_analysis",
                "base_exit_code": 0,
                "head_exit_code": 1,
            }],
            [{
                "evidence_type": "differential_execution",
                "verdict": "AMBIGUOUS",
                "base_exit_code": 1,
                "head_exit_code": 1,
            }],
        ],
        ids=[
            "empty",
            "base_pass_head_fail_without_exits",
            "differential_regression_without_exits",
            "static_only_with_exits",
            "ambiguous_with_exits",
        ],
    )
    def test_has_real_execution_evidence_refuses(
        self, records: list[dict[str, Any]]
    ) -> None:
        assert not _has_real_execution_evidence(records)

    @pytest.mark.parametrize(
        "record",
        [
            {
                "evidence_type": "base_pass_head_fail",
                "base_exit_code": 0,
                "head_exit_code": 1,
            },
            {
                "evidence_type": "differential_execution",
                "verdict": "REGRESSION",
                "base_exit_code": 0,
                "head_exit_code": 1,
            },
        ],
        ids=["base_pass_head_fail", "differential_regression"],
    )
    def test_has_real_execution_evidence_accepts_recorded_runs(
        self, record: dict[str, Any]
    ) -> None:
        assert _has_real_execution_evidence([record])

    def test_condition_two_requires_real_recorded_exits(self) -> None:
        without_exits = _check_blocker_conditions(
            _blocker_candidate(),
            [APPROVED_AUTH],
            [{"evidence_type": "base_pass_head_fail", "verdict": "REGRESSION"}],
            GENERATED_TESTS,
            CHANGED_FILES,
        )
        assert not without_exits["blocker_conditions"]["2_base_head_execution"]
        assert not without_exits["all_blocker_conditions_met"]

        with_exits = _check_blocker_conditions(
            _blocker_candidate(),
            [APPROVED_AUTH],
            [_real_regression_record()],
            GENERATED_TESTS,
            CHANGED_FILES,
        )
        assert with_exits["blocker_conditions"]["2_base_head_execution"]
        assert with_exits["all_blocker_conditions_met"]

    def test_static_evidence_type_never_satisfies_condition_two(self) -> None:
        check = _check_blocker_conditions(
            _blocker_candidate(evidence_type="static_analysis"),
            [APPROVED_AUTH],
            [_real_regression_record()],
            GENERATED_TESTS,
            CHANGED_FILES,
        )
        assert not check["blocker_conditions"]["2_base_head_execution"]

    def test_required_evidence_types_are_runtime_kinds(self) -> None:
        assert sorted(BLOCKER_REQUIRED_EVIDENCE_TYPES) == [
            "base_pass_head_fail",
            "differential_execution",
        ]


class TestRealExecutionEvidencePositiveControl:
    """(c) With a real base_pass_head_fail run, BLOCKER is reachable."""

    def test_policy_publishes_blocker_with_real_execution_evidence(self) -> None:
        result = policy_recalculate(
            [_blocker_candidate()],
            contracts=[APPROVED_AUTH],
            diff_results=[_real_regression_record()],
            generated_tests_path=GENERATED_TESTS,
            changed_files=CHANGED_FILES,
        )
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "BLOCKER"
        blocker_check = confirmed["blocker_check"]
        assert blocker_check["all_blocker_conditions_met"]
        conditions = blocker_check["blocker_conditions"]
        assert all(conditions.values())
        assert set(conditions) == {
            "1_approved_contract",
            "2_base_head_execution",
            "3_attribution_to_head",
            "4_db_behavior_evidence",
            "5_capsule_replayable",
            "6_confidence_090",
        }

    def test_court_node_publishes_blocker_with_real_execution_evidence(self) -> None:
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [],
            "diff_results": [_real_regression_record()],
            "contracts": [APPROVED_AUTH],
            "generated_tests_path": GENERATED_TESTS,
        }
        result = run_review_court(cast(Phase0State, state))
        assert len(result["confirmed_findings"]) == 1
        assert result["confirmed_findings"][0]["severity"] == "BLOCKER"


class TestStaticConfidenceCeiling:
    """(d) Static evidence reaches at most MAJOR with confidence <= 0.85."""

    def test_node_and_policy_ceilings_are_one_source_of_truth(self) -> None:
        assert run_static_checks._STATIC_CONFIDENCE_CEILING == STATIC_CONFIDENCE_CEILING
        assert STATIC_CONFIDENCE_CEILING == 0.85

    def test_policy_caps_static_severity_and_confidence(self) -> None:
        result = policy_recalculate([_static_candidate()])
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "MAJOR"
        assert confirmed["confidence"] == STATIC_CONFIDENCE_CEILING

    def test_static_check_node_caps_blocker_and_confidence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fabricated = {
            "id": "STATIC-FAB-01",
            "contract_id": "AUTH-01",
            "severity": "BLOCKER",
            "type": "annotation_removed",
            "description": "fabricated checker output (worst-case static evidence)",
            "evidence_type": "java_source_diff",
            "confidence": 1.0,
            "location": "AuthController.java",
            "source": "static_analysis",
        }
        monkeypatch.setattr(
            run_static_checks,
            "run_contract_checks",
            lambda base_files, head_files: [dict(fabricated)],
        )
        base_ws = tmp_path / "base"
        head_ws = tmp_path / "head"
        for ws in (base_ws, head_ws):
            (ws / "src" / "main" / "java").mkdir(parents=True)
        state: dict[str, Any] = {
            "base_workspace": str(base_ws),
            "head_workspace": str(head_ws),
            "app_dir": "",
            "contracts": [],
        }
        result = run_static_checks.run_static_checks_node(cast(Phase0State, state))
        assert len(result["static_findings"]) == 1
        finding = result["static_findings"][0]
        assert finding["severity"] == "MAJOR"
        assert finding["severity"] != "BLOCKER"
        assert finding["confidence"] <= run_static_checks._STATIC_CONFIDENCE_CEILING
        assert "BLOCKER" in finding["p0_5_note"]
