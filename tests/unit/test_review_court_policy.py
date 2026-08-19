"""Pure-function matrix for the deterministic Review Court policy layer.

Covers the §14.1 split: severity/status are recomputed by
policy_recalculate (never by the model layer), the preexisting-defect rule,
parse-failure safety, model-ignored audit retention, policy idempotency and
legacy-path compatibility.
"""
import copy
import hashlib
import json
from typing import Any

from agent.review_court.policy import (
    NOT_ATTRIBUTED_SEVERITY,
    NOT_ATTRIBUTED_STATUS,
    policy_recalculate,
)


def _diff_record(**overrides: Any) -> dict[str, Any]:
    """A runtime diff record where Base and Head both fail the same way."""
    record: dict[str, Any] = {
        "contract_id": "AUTH-01",
        "experiment_id": "DIFF-01",
        "verdict": "AMBIGUOUS",
        "detail": "Test fails in both Base and Head",
        "severity": "MINOR",
        "confidence": 0.65,
        "evidence_type": "differential_execution",
        "base_exit_code": 1,
        "head_exit_code": 1,
        "base_test_counts": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
        "head_test_counts": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
        "base_output": "java.lang.AssertionError: expected:<allowed> but was:<denied>",
        "head_output": "java.lang.AssertionError: expected:<allowed> but was:<denied>",
        "base_db_snapshot": {"method": "file", "rows": {"orders": []}},
        "head_db_snapshot": {"method": "file", "rows": {"orders": []}},
        "db_state_verdict": "DB_CLEAN",
        "evidence_digest": "sha256:record",
    }
    record.update(overrides)
    return record


def _diff_candidate(**overrides: Any) -> dict[str, Any]:
    """A differential candidate mirroring the node's candidate assembly."""
    candidate: dict[str, Any] = {
        "id": "COURT-AUTH-01",
        "contract_id": "AUTH-01",
        "severity": "MINOR",
        "type": "differential_regression",
        "description": "Test fails in both Base and Head",
        "evidence_type": "differential_execution",
        "confidence": 0.65,
        "source": "differential",
        "status": "candidate",
        "diff_verdict": "AMBIGUOUS",
        "db_state_verdict": "DB_CLEAN",
        "location": "",
        "evidence_digest": "",
        "diff_result_index": 0,
        "base_exit_code": 1,
        "head_exit_code": 1,
        "base_test_counts": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
        "head_test_counts": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
        "base_output": "java.lang.AssertionError: expected:<allowed> but was:<denied>",
        "head_output": "java.lang.AssertionError: expected:<allowed> but was:<denied>",
        "base_db_snapshot": {"method": "file", "rows": {"orders": []}},
        "head_db_snapshot": {"method": "file", "rows": {"orders": []}},
    }
    candidate.update(overrides)
    return candidate


def _static_candidate(**overrides: Any) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "id": "STATIC-AUTH-01",
        "contract_id": "AUTH-01",
        "severity": "BLOCKER",
        "type": "annotation_removed",
        "description": "@PreAuthorize removed from controller method",
        "evidence_type": "static_regex_analysis",
        "confidence": 0.95,
        "source": "static_analysis",
        "status": "candidate",
    }
    candidate.update(overrides)
    return candidate


def _recalculate(candidates: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """policy_recalculate with policy-only defaults (no model, no context)."""
    defaults: dict[str, Any] = {
        "model_output": None,
        "contracts": [],
        "diff_results": [],
        "generated_tests_path": "",
        "changed_files": [],
    }
    defaults.update(kwargs)
    return policy_recalculate(candidates, **defaults)


def _legacy_digest(finding: dict[str, Any]) -> str:
    """The exact legacy digest payload, re-derived for byte-compat checks."""
    payload = json.dumps({
        "id": finding.get("id", ""),
        "evidence_type": finding.get("evidence_type", ""),
        "severity": finding.get("severity"),
        "confidence": finding.get("confidence"),
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


class TestPreexistingDefect:
    """Base also fails → downgrade unless a distinct head-only difference."""

    def test_same_failure_both_sides_downgrades_to_not_attributed(self):
        candidate = _diff_candidate()
        result = _recalculate([candidate], diff_results=[_diff_record()])

        assert result["confirmed_findings"] == []
        audit = result["audit_entries"][0]
        assert audit["final_status"] == NOT_ATTRIBUTED_STATUS
        assert audit["final_severity"] == NOT_ATTRIBUTED_SEVERITY
        assert audit["preexisting_check"]["head_only_difference"] is False
        assert result["candidate_findings"][0]["policy_outcome"] == NOT_ATTRIBUTED_STATUS

    def test_downgraded_confidence_is_bounded(self):
        candidate = _diff_candidate(confidence=0.9)
        result = _recalculate([candidate], diff_results=[_diff_record()])
        assert result["audit_entries"][0]["final_confidence"] <= 0.5

    def test_head_only_db_mutation_keeps_severity(self):
        candidate = _diff_candidate(severity="MAJOR", confidence=0.88)
        record = _diff_record(head_db_snapshot={"method": "file", "rows": {"orders": ["row1"]}})
        result = _recalculate([candidate], diff_results=[record])

        audit = result["audit_entries"][0]
        assert audit["final_status"] == "confirmed"
        assert audit["final_severity"] == "MAJOR"
        assert audit["preexisting_check"]["head_only_difference"] is True
        assert "head_db_state_differs" in audit["preexisting_check"]["head_only_signals"]
        assert result["confirmed_findings"][0]["severity"] == "MAJOR"

    def test_head_only_different_failure_signature_keeps_attribution(self):
        candidate = _diff_candidate(severity="MAJOR", confidence=0.88)
        record = _diff_record(
            head_output="java.lang.AssertionError: expected:<guest> but was:<admin>",
        )
        result = _recalculate([candidate], diff_results=[record])

        assert result["audit_entries"][0]["final_status"] == "confirmed"
        signals = result["audit_entries"][0]["preexisting_check"]["head_only_signals"]
        assert "failure_signature_differs" in signals

    def test_head_extra_failure_keeps_attribution(self):
        candidate = _diff_candidate(severity="MAJOR", confidence=0.88)
        record = _diff_record(
            head_test_counts={"tests": 2, "failures": 2, "errors": 0, "skipped": 0},
        )
        result = _recalculate([candidate], diff_results=[record])

        signals = result["audit_entries"][0]["preexisting_check"]["head_only_signals"]
        assert "head_extra_failure_count" in signals
        assert result["audit_entries"][0]["final_status"] == "confirmed"

    def test_different_exit_codes_keep_attribution(self):
        candidate = _diff_candidate(severity="MAJOR", confidence=0.88, head_exit_code=137)
        record = _diff_record(head_exit_code=137)
        result = _recalculate([candidate], diff_results=[record])

        signals = result["audit_entries"][0]["preexisting_check"]["head_only_signals"]
        assert "exit_code_differs" in signals
        assert result["audit_entries"][0]["final_status"] == "confirmed"

    def test_base_pass_head_fail_is_not_preexisting(self):
        candidate = _diff_candidate(
            severity="MAJOR",
            confidence=0.88,
            evidence_type="base_pass_head_fail",
            diff_verdict="REGRESSION",
            base_exit_code=0,
            head_exit_code=1,
        )
        record = _diff_record(
            verdict="REGRESSION",
            evidence_type="base_pass_head_fail",
            base_exit_code=0,
            head_exit_code=1,
        )
        result = _recalculate([candidate], diff_results=[record])

        audit = result["audit_entries"][0]
        assert audit["final_status"] == "confirmed"
        assert audit["preexisting_check"] is None

    def test_static_candidate_linked_to_base_fail_record_downgrades(self):
        candidate = _static_candidate(severity="MAJOR", confidence=0.85)
        result = _recalculate([candidate], diff_results=[_diff_record()])

        audit = result["audit_entries"][0]
        assert audit["final_status"] == NOT_ATTRIBUTED_STATUS
        assert audit["final_severity"] == NOT_ATTRIBUTED_SEVERITY
        assert result["confirmed_findings"] == []

    def test_embedded_runtime_fields_work_without_diff_results(self):
        candidate = _diff_candidate()
        candidate.pop("diff_result_index")
        result = _recalculate([candidate], diff_results=[])

        assert result["audit_entries"][0]["final_status"] == NOT_ATTRIBUTED_STATUS

    def test_missing_exit_codes_rule_does_not_fire(self):
        """Without recorded exit codes the legacy AMBIGUOUS path is unchanged."""
        candidate = _diff_candidate(
            base_exit_code=None,
            head_exit_code=None,
            base_output="",
            head_output="",
        )
        record = _diff_record()
        record.pop("base_exit_code")
        record.pop("head_exit_code")
        result = _recalculate([candidate], diff_results=[record])

        confirmed = result["confirmed_findings"]
        assert len(confirmed) == 1
        assert confirmed[0]["status"] == "confirmed"
        assert confirmed[0]["severity"] == "MINOR"
        assert result["audit_entries"][0]["preexisting_check"] is None

    def test_audit_records_the_comparison(self):
        result = _recalculate([_diff_candidate()], diff_results=[_diff_record()])
        check = result["audit_entries"][0]["preexisting_check"]
        assert check["base_exit_code"] == 1
        assert check["head_exit_code"] == 1
        assert "AssertionError" in check["base_failure_signature"]
        assert "AssertionError" in check["head_failure_signature"]
        assert check["head_only_signals"] == []


class TestParseFailure:
    """Model parse failures must never auto-confirm."""

    def test_parse_failure_never_confirms(self):
        model_output = {"defense_materials": [], "parse_failed": True, "error": ""}
        result = _recalculate(
            [_static_candidate()], model_output=model_output
        )

        confirmed = result["confirmed_findings"]
        assert len(confirmed) == 1
        assert confirmed[0]["status"] == "needs_confirmation"
        assert confirmed[0]["severity"] == "MAJOR"  # BLOCKER capped for human review
        assert confirmed[0]["confidence"] <= 0.8
        assert result["audit_entries"][0]["final_status"] == "needs_confirmation"

    def test_parse_failure_keeps_non_blocker_severity(self):
        model_output = {"defense_materials": [], "parse_failed": True, "error": ""}
        result = _recalculate(
            [_static_candidate(severity="MINOR", confidence=0.7)],
            model_output=model_output,
        )
        assert result["confirmed_findings"][0]["status"] == "needs_confirmation"
        assert result["confirmed_findings"][0]["severity"] == "MINOR"

    def test_model_error_falls_back_to_deterministic(self):
        model_output = {
            "defense_materials": [],
            "parse_failed": False,
            "error": "provider unavailable",
        }
        result = _recalculate(
            [_static_candidate()], model_output=model_output
        )

        confirmed = result["confirmed_findings"]
        assert len(confirmed) == 1
        assert confirmed[0]["status"] == "confirmed"
        assert confirmed[0]["severity"] == "MAJOR"
        assert result["audit_entries"][0]["model_error"] == "provider unavailable"


class TestModelIgnoredAudit:
    """Model-ignored candidates are still policy-evaluated and audited."""

    def _two_candidates(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        static = _static_candidate(contract_id="", confidence=0.85, severity="MAJOR")
        diff = _diff_candidate(
            id="COURT-DIFF-01",
            contract_id="DIFF-01",
            severity="MAJOR",
            confidence=0.88,
            evidence_type="base_pass_head_fail",
            diff_verdict="REGRESSION",
            base_exit_code=0,
            head_exit_code=1,
        )
        record = _diff_record(
            contract_id="DIFF-01",
            verdict="REGRESSION",
            evidence_type="base_pass_head_fail",
            base_exit_code=0,
            head_exit_code=1,
        )
        return [static, diff], [record]

    def test_model_ignored_candidate_still_policy_evaluated(self):
        candidates, records = self._two_candidates()
        model_output = {
            "defense_materials": [
                {"id": "STATIC-AUTH-01", "defense_argument": "refactor only",
                 "candidate_confidence": None, "is_false_positive": None},
            ],
            "parse_failed": False,
            "error": "",
        }
        result = _recalculate(
            candidates, model_output=model_output, diff_results=records
        )

        by_id = {a["id"]: a for a in result["audit_entries"]}
        assert by_id["COURT-DIFF-01"]["model_ignored"] is True
        assert by_id["COURT-DIFF-01"]["final_status"] == "confirmed"
        confirmed_ids = {f["id"] for f in result["confirmed_findings"]}
        assert "COURT-DIFF-01" in confirmed_ids

    def test_model_ignored_candidate_audited(self):
        candidates, records = self._two_candidates()
        model_output = {
            "defense_materials": [
                {"id": "STATIC-AUTH-01", "defense_argument": "arg",
                 "candidate_confidence": None, "is_false_positive": None},
            ],
            "parse_failed": False,
            "error": "",
        }
        result = _recalculate(
            candidates, model_output=model_output, diff_results=records
        )
        by_id = {a["id"]: a for a in result["audit_entries"]}
        assert by_id["COURT-DIFF-01"]["defense_argument"] == ""
        assert len(result["audit_entries"]) == 2

    def test_model_advisory_false_positive_does_not_dismiss(self):
        model_output = {
            "defense_materials": [
                {"id": "STATIC-AUTH-01", "defense_argument": "arg",
                 "candidate_confidence": None, "is_false_positive": True},
            ],
            "parse_failed": False,
            "error": "",
        }
        result = _recalculate(
            [_static_candidate()], model_output=model_output
        )
        assert result["confirmed_findings"][0]["status"] == "confirmed"
        assert result["audit_entries"][0]["model_advisory_false_positive"] is True

    def test_model_confidence_clamped_by_static_ceiling(self):
        model_output = {
            "defense_materials": [
                {"id": "STATIC-AUTH-01", "defense_argument": "arg",
                 "candidate_confidence": 0.99, "is_false_positive": None},
            ],
            "parse_failed": False,
            "error": "",
        }
        result = _recalculate(
            [_static_candidate()], model_output=model_output
        )
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "MAJOR"
        assert confirmed["confidence"] <= 0.85

    def test_defense_argument_recorded_on_confirmed_finding(self):
        model_output = {
            "defense_materials": [
                {"id": "STATIC-AUTH-01", "defense_argument": "equivariant",
                 "candidate_confidence": None, "is_false_positive": None},
            ],
            "parse_failed": False,
            "error": "",
        }
        result = _recalculate(
            [_static_candidate()], model_output=model_output
        )
        assert result["confirmed_findings"][0]["defense_argument"] == "equivariant"


class TestLegacyCompat:
    """Cases without the new rules must keep the legacy policy byte-compatible."""

    def test_static_blocker_capped_major(self):
        result = _recalculate([_static_candidate()])
        confirmed = result["confirmed_findings"][0]
        assert confirmed["status"] == "confirmed"
        assert confirmed["severity"] == "MAJOR"
        assert confirmed["confidence"] <= 0.85
        assert confirmed["blocker_check"]["all_blocker_conditions_met"] is False

    def test_blocker_six_conditions_confirmed(self):
        candidate = _diff_candidate(
            severity="BLOCKER",
            confidence=0.95,
            evidence_type="base_pass_head_fail",
            diff_verdict="REGRESSION",
            base_exit_code=0,
            head_exit_code=1,
            db_state_verdict="DB_MUTATED_ON_UNAUTH",
            location="src/AuthController.java",
        )
        record = _diff_record(
            verdict="REGRESSION",
            evidence_type="base_pass_head_fail",
            base_exit_code=0,
            head_exit_code=1,
            db_state_verdict="DB_MUTATED_ON_UNAUTH",
        )
        result = _recalculate(
            [candidate],
            contracts=[{"id": "AUTH-01", "approved": True}],
            diff_results=[record],
            generated_tests_path="capsules/tests/AuthFlowTest.java",
            changed_files=["src/AuthController.java"],
        )
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "BLOCKER"
        assert confirmed["blocker_check"]["all_blocker_conditions_met"] is True

    def test_blocker_missing_conditions_downgraded_major(self):
        candidate = _diff_candidate(
            severity="BLOCKER",
            confidence=0.95,
            evidence_type="base_pass_head_fail",
            diff_verdict="REGRESSION",
            base_exit_code=0,
            head_exit_code=1,
            db_state_verdict="",
            location="src/AuthController.java",
        )
        record = _diff_record(
            verdict="REGRESSION",
            evidence_type="base_pass_head_fail",
            base_exit_code=0,
            head_exit_code=1,
            db_state_verdict="",
        )
        result = _recalculate(
            [candidate],
            contracts=[{"id": "AUTH-01", "approved": True}],
            diff_results=[record],
            changed_files=["src/AuthController.java"],
        )
        confirmed = result["confirmed_findings"][0]
        assert confirmed["severity"] == "MAJOR"
        assert confirmed["confidence"] <= 0.88

    def test_legacy_integration_scenario_unchanged(self):
        """The exact pre-split test_differential scenario, as a pure matrix."""
        static = {
            "id": "STATIC-AUTH-01",
            "severity": "BLOCKER",
            "type": "annotation_removed",
            "description": "@PreAuthorize removed from controller method",
            "evidence_type": "static_regex_analysis",
            "confidence": 0.95,
            "source": "static_analysis",
            "status": "candidate",
        }
        diff = {
            "id": "COURT-DIFF-HTTP",
            "contract_id": "DIFF-HTTP",
            "severity": "MAJOR",
            "type": "differential_regression",
            "description": "Security annotation present in base but missing in head",
            "evidence_type": "base_pass_head_fail",
            "confidence": 0.88,
            "source": "differential",
            "status": "candidate",
            "diff_verdict": "REGRESSION",
            "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
            "location": "",
            "evidence_digest": "",
        }
        result = _recalculate(
            [static, diff],
            contracts=[{"id": "AUTH-01", "description": "所有变更API端点必须要求认证"}],
            diff_results=[{
                "contract_id": "DIFF-HTTP",
                "verdict": "REGRESSION",
                "detail": "Security annotation present in base but missing in head",
                "evidence_type": "base_pass_head_fail",
                "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
            }],
        )
        confirmed = result["confirmed_findings"]
        assert len(confirmed) == 2
        static_confirmed = [f for f in confirmed if f.get("source") == "static_analysis"]
        for sf in static_confirmed:
            assert sf.get("severity") != "BLOCKER"
        assert all(f.get("severity") != "BLOCKER" for f in confirmed)

    def test_digest_matches_legacy_payload(self):
        result = _recalculate([_static_candidate()])
        confirmed = result["confirmed_findings"][0]
        assert confirmed["evidence_digest"] == _legacy_digest(confirmed)

    def test_confirmed_keeps_legacy_fields(self):
        result = _recalculate([_static_candidate()])
        confirmed = result["confirmed_findings"][0]
        for key in (
            "id", "contract_id", "severity", "confidence", "status",
            "evidence_digest", "blocker_check", "court_source", "source",
            "type", "evidence_type",
        ):
            assert key in confirmed
        assert confirmed["court_source"] == "rule_based"
        assert confirmed["status"] == "confirmed"


class TestPolicyProperties:
    """Purity, idempotency and audit completeness."""

    def test_idempotent(self):
        candidates = [_static_candidate(), _diff_candidate()]
        records = [_diff_record()]
        kwargs: dict[str, Any] = {
            "contracts": [{"id": "AUTH-01", "approved": True}],
            "diff_results": records,
            "generated_tests_path": "capsules/tests/AuthFlowTest.java",
            "changed_files": ["src/AuthController.java"],
        }
        first = policy_recalculate(candidates, **kwargs)
        second = policy_recalculate(candidates, **kwargs)
        assert first == second

    def test_does_not_mutate_inputs(self):
        candidates = [_static_candidate(), _diff_candidate()]
        records = [_diff_record()]
        candidates_before = copy.deepcopy(candidates)
        records_before = copy.deepcopy(records)
        policy_recalculate(candidates, diff_results=records)
        assert candidates == candidates_before
        assert records == records_before

    def test_empty_candidates(self):
        result = _recalculate([])
        assert result["candidate_findings"] == []
        assert result["confirmed_findings"] == []
        assert result["audit_entries"] == []

    def test_non_reproducible_skipped_but_audited(self):
        candidate = _diff_candidate(diff_verdict="NON_REPRODUCIBLE")
        result = _recalculate([candidate])
        assert result["confirmed_findings"] == []
        audit = result["audit_entries"][0]
        assert audit["final_status"] == "skipped"
        assert audit["skip_reason"] == "diff_verdict=NON_REPRODUCIBLE"

    def test_audit_covers_every_candidate(self):
        result = _recalculate([_static_candidate(), _diff_candidate()])
        assert len(result["audit_entries"]) == 2
        assert {a["id"] for a in result["audit_entries"]} == {
            "STATIC-AUTH-01", "COURT-AUTH-01",
        }


class TestNodeOrchestration:
    """The node defaults to deterministic and audits everything."""

    def test_review_court_node_default_deterministic_and_audits(self):
        from agent.nodes.review_court import review_court_node

        state = {
            "static_findings": [{
                "id": "STATIC-AUTH-01",
                "severity": "BLOCKER",
                "type": "annotation_removed",
                "description": "@PreAuthorize removed from controller method",
                "evidence_type": "static_regex_analysis",
                "confidence": 0.95,
            }],
            "diff_results": [{
                "contract_id": "DIFF-HTTP",
                "verdict": "REGRESSION",
                "detail": "Security annotation present in base but missing in head",
                "evidence_type": "base_pass_head_fail",
                "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
            }],
            "contracts": [{"id": "AUTH-01", "description": "认证契约"}],
        }
        result = review_court_node(state)
        assert "court_audit" in result
        assert len(result["court_audit"]) == len(result["candidate_findings"]) == 2
        assert len(result["confirmed_findings"]) == 2
        assert all(f["status"] == "confirmed" for f in result["confirmed_findings"])

    def test_injected_producer_sees_all_candidates(self):
        from agent.nodes.review_court import run_review_court

        captured: dict[str, Any] = {}

        def producer(candidates: list[dict[str, Any]], _state: dict[str, Any]) -> dict[str, Any]:
            captured["n"] = len(candidates)
            return {
                "defense_materials": [
                    {"id": "STATIC-AUTH-01", "defense_argument": "arg",
                     "candidate_confidence": None, "is_false_positive": None},
                ],
                "parse_failed": False,
                "error": "",
            }

        state = {
            "static_findings": [{
                "id": "STATIC-AUTH-01",
                "severity": "MAJOR",
                "type": "annotation_removed",
                "description": "@PreAuthorize removed",
                "evidence_type": "static_regex_analysis",
                "confidence": 0.8,
            }],
            "diff_results": [{
                "contract_id": "DIFF-HTTP",
                "verdict": "REGRESSION",
                "detail": "regression",
                "evidence_type": "base_pass_head_fail",
                "confidence": 0.88,
                "db_state_verdict": "",
            }],
            "contracts": [],
        }
        result = run_review_court(state, model_produce_defense=producer)
        assert captured["n"] == 2
        by_id = {a["id"]: a for a in result["court_audit"]}
        assert by_id["COURT-DIFF-HTTP"]["model_ignored"] is True
        assert len(result["confirmed_findings"]) == 2

    def test_async_producer_supported(self):
        from agent.nodes.review_court import run_review_court

        async def producer(
            candidates: list[dict[str, Any]], _state: dict[str, Any]
        ) -> dict[str, Any]:
            assert len(candidates) == 1
            return {"defense_materials": [], "parse_failed": False, "error": ""}

        state = {
            "static_findings": [{
                "id": "STATIC-AUTH-01",
                "severity": "MAJOR",
                "type": "annotation_removed",
                "description": "@PreAuthorize removed",
                "evidence_type": "static_regex_analysis",
                "confidence": 0.8,
            }],
            "diff_results": [],
            "contracts": [],
        }
        result = run_review_court(state, model_produce_defense=producer)
        assert len(result["confirmed_findings"]) == 1
        assert result["confirmed_findings"][0]["status"] == "confirmed"

