"""Attribution split tests for go-nogo #3 (case-att-08 both-fail).

Pins the engine-side split that unmasks a head-introduced failure when
Base AND Head each fail their own contract (case-att-08: Base fails
UNIQUE-01 pre-existing, Head fails EVENT_ONCE-01 introduced):

- the pure splitter groups test methods by per-side pass/fail;
- surefire XML parsing feeds the splitter (missing report -> None);
- the contract mapping keeps UNIQUE/EVENT attribution correct;
- the Review Court confirms the head-only REGRESSION finding for
  EVENT_ONCE-01 and never attributes the base-only UNIQUE-01 failure;
- without per-method evidence the legacy whole-run AMBIGUOUS path stays.

No Maven, no LLM, no git: everything runs offline.
"""
from pathlib import Path
from typing import Any, cast

from agent.nodes.review_court import run_review_court
from agent.nodes.run_differential import (
    _both_fail_method_groups,
    _contract_for_test_method,
    _split_both_fail_groups,
    _split_entry_digest,
    _test_failure_details,
    _test_outcomes,
)
from agent.state import Phase0State

TEST_CLASS = "SpecProofGeneratedTest"

SUREFIRE_BASE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.specproof.demo.SpecProofGeneratedTest"
           tests="4" failures="1" errors="0">
  <testcase name="duplicateEmailChangeMustBeRejected"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0">
    <failure message="duplicate accepted"
             type="java.lang.AssertionError">stack</failure>
  </testcase>
  <testcase name="freshEmailChangeMustSucceed"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0"/>
  <testcase name="emailChangeEventMustGoToExpectedRoutingKey"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0"/>
  <testcase name="emailChangeEventPayloadMustBeIntact"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0"/>
</testsuite>
"""

SUREFIRE_HEAD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.specproof.demo.SpecProofGeneratedTest"
           tests="4" failures="1" errors="0">
  <testcase name="duplicateEmailChangeMustBeRejected"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0"/>
  <testcase name="freshEmailChangeMustSucceed"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0"/>
  <testcase name="emailChangeEventMustGoToExpectedRoutingKey"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0">
    <failure message="routing key mismatch"
             type="java.lang.AssertionError">stack</failure>
  </testcase>
  <testcase name="emailChangeEventPayloadMustBeIntact"
            classname="com.specproof.demo.SpecProofGeneratedTest" time="1.0"/>
</testsuite>
"""


def _write_surefire_report(root: Path, side: str, content: str) -> Path:
    # Surefire's real naming: TEST-<fully.qualified.ClassName>.xml — the
    # generated test lives in package com.specproof.demo. This exact shape
    # is what broke the bare-name lookup (the bug this suite pins).
    report = (
        root / side / "target" / "surefire-reports"
        / f"TEST-com.specproof.demo.{TEST_CLASS}.xml"
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(content, encoding="utf-8")
    return report


class TestBothFailSplitter:
    def test_groups_split_head_and_base_failures(self) -> None:
        base = {
            "duplicateEmailChangeMustBeRejected": "fail",
            "freshEmailChangeMustSucceed": "pass",
            "emailChangeEventMustGoToExpectedRoutingKey": "pass",
        }
        head = {
            "duplicateEmailChangeMustBeRejected": "pass",
            "freshEmailChangeMustSucceed": "pass",
            "emailChangeEventMustGoToExpectedRoutingKey": "fail",
        }
        head_only, base_only, both = _split_both_fail_groups(base, head)
        assert head_only == ["emailChangeEventMustGoToExpectedRoutingKey"]
        assert base_only == ["duplicateEmailChangeMustBeRejected"]
        assert both == []

    def test_skipped_on_base_is_ambiguous(self) -> None:
        assert _split_both_fail_groups({"m": "skipped"}, {"m": "fail"}) == (
            [], [], ["m"],
        )

    def test_missing_on_base_is_ambiguous(self) -> None:
        assert _split_both_fail_groups({}, {"m": "fail"}) == ([], [], ["m"])

    def test_fail_on_both_stays_ambiguous(self) -> None:
        assert _split_both_fail_groups({"m": "fail"}, {"m": "fail"}) == (
            [], [], ["m"],
        )


class TestSurefireParsing:
    def test_test_outcomes_parses_surefire_xml(self, tmp_path: Path) -> None:
        _write_surefire_report(tmp_path, "base", SUREFIRE_BASE_XML)
        outcomes = _test_outcomes(str(tmp_path / "base"), TEST_CLASS)
        assert outcomes == {
            "duplicateEmailChangeMustBeRejected": "fail",
            "freshEmailChangeMustSucceed": "pass",
            "emailChangeEventMustGoToExpectedRoutingKey": "pass",
            "emailChangeEventPayloadMustBeIntact": "pass",
        }

    def test_both_fail_groups_from_reports(self, tmp_path: Path) -> None:
        _write_surefire_report(tmp_path, "base", SUREFIRE_BASE_XML)
        _write_surefire_report(tmp_path, "head", SUREFIRE_HEAD_XML)
        groups = _both_fail_method_groups(
            str(tmp_path / "base"), str(tmp_path / "head"), TEST_CLASS
        )
        assert groups is not None
        head_only, base_only, both = groups
        assert head_only == ["emailChangeEventMustGoToExpectedRoutingKey"]
        assert base_only == ["duplicateEmailChangeMustBeRejected"]
        assert both == []

    def test_missing_reports_fall_back_to_none(self, tmp_path: Path) -> None:
        assert (
            _both_fail_method_groups(
                str(tmp_path / "base"), str(tmp_path / "head"), TEST_CLASS
            )
            is None
        )

    def test_bare_class_name_report_still_supported(self, tmp_path: Path) -> None:
        # Default-package reports (TEST-<Class>.xml) must keep working.
        report = tmp_path / "base" / "target" / "surefire-reports" / (
            f"TEST-{TEST_CLASS}.xml"
        )
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(SUREFIRE_BASE_XML, encoding="utf-8")
        outcomes = _test_outcomes(str(tmp_path / "base"), TEST_CLASS)
        assert outcomes["duplicateEmailChangeMustBeRejected"] == "fail"
        assert outcomes["freshEmailChangeMustSucceed"] == "pass"

    def test_failure_details_extracted_per_method(self, tmp_path: Path) -> None:
        _write_surefire_report(tmp_path, "base", SUREFIRE_BASE_XML)
        details = _test_failure_details(str(tmp_path / "base"), TEST_CLASS)
        assert set(details) == {"duplicateEmailChangeMustBeRejected"}
        snippet = details["duplicateEmailChangeMustBeRejected"]
        assert "java.lang.AssertionError" in snippet
        assert "duplicate accepted" in snippet


class TestContractMapping:
    def test_att08_methods_map_to_their_contracts(self) -> None:
        assert (
            _contract_for_test_method("duplicateEmailChangeMustBeRejected")
            == "UNIQUE-01"
        )
        assert (
            _contract_for_test_method(
                "emailChangeEventMustGoToExpectedRoutingKey"
            )
            == "EVENT_ONCE-01"
        )


class TestSplitDigest:
    def test_split_entry_digest_deterministic(self) -> None:
        kwargs = {
            "verdict": "REGRESSION",
            "contract_id": "EVENT_ONCE-01",
            "method": "emailChangeEventMustGoToExpectedRoutingKey",
            "base_status": "pass",
            "head_status": "fail",
            "base_run_exit": 1,
            "head_run_exit": 1,
            "base_result": {"test_counts": {"tests": 4, "failures": 1}},
            "head_result": {"test_counts": {"tests": 4, "failures": 1}},
            "base_snapshot": {"rows": {}},
            "head_snapshot": {"rows": {}},
            "test_sha": "abc123",
        }
        assert _split_entry_digest(**kwargs) == _split_entry_digest(**kwargs)
        assert _split_entry_digest(**kwargs).startswith("sha256:")


class TestReviewCourtAttribution:
    """The court attributes the head-only split entry, never the base-only."""

    def _split_diff_results(self) -> list[dict[str, Any]]:
        return [
            {
                "contract_id": "EVENT_ONCE-01",
                "experiment_id": "DIFF-01",
                "verdict": "REGRESSION",
                "detail": (
                    "Split differential: test method "
                    "emailChangeEventMustGoToExpectedRoutingKey passes on "
                    "Base but fails on Head — head-introduced failure for "
                    "EVENT_ONCE-01 (whole-run exits: base 1, head 1)"
                ),
                "severity": "MAJOR",
                "confidence": 0.88,
                "evidence_type": "base_pass_head_fail",
                "base_exit_code": 0,
                "head_exit_code": 1,
                "method_scoped": True,
                "base_method_status": "pass",
                "head_method_status": "fail",
                "whole_run_base_exit_code": 1,
                "whole_run_head_exit_code": 1,
                "base_db_snapshot": {},
                "head_db_snapshot": {},
                "db_state_verdict": "DB_CONSISTENT",
                "evidence_digest": "sha256:split-event",
            },
            {
                "contract_id": "UNIQUE-01",
                "experiment_id": "DIFF-01",
                "verdict": "UNEXPECTED_FIX",
                "detail": (
                    "Split differential: test method "
                    "duplicateEmailChangeMustBeRejected fails on Base but "
                    "passes on Head — pre-existing base-side failure for "
                    "UNIQUE-01, not attributed to the reviewed head "
                    "(whole-run exits: base 1, head 1)"
                ),
                "severity": "NONE",
                "confidence": 0.80,
                "evidence_type": "differential_execution",
                "base_exit_code": 1,
                "head_exit_code": 0,
                "method_scoped": True,
                "base_method_status": "fail",
                "head_method_status": "pass",
                "whole_run_base_exit_code": 1,
                "whole_run_head_exit_code": 1,
                "base_db_snapshot": {},
                "head_db_snapshot": {},
                "db_state_verdict": "DB_CONSISTENT",
                "evidence_digest": "sha256:split-unique",
            },
        ]

    def test_court_confirms_head_only_split_entry_only(self) -> None:
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [],
            "diff_results": self._split_diff_results(),
            "contracts": [
                {"id": "EVENT_ONCE-01", "approved": True},
                {"id": "UNIQUE-01", "approved": True},
            ],
            "generated_tests_path": "capsules/tests/SpecProofGeneratedTest.java",
        }
        result = run_review_court(cast(Phase0State, state))

        confirmed_contracts = {
            str(f.get("contract_id")) for f in result["confirmed_findings"]
        }
        assert confirmed_contracts == {"EVENT_ONCE-01"}
        finding = result["confirmed_findings"][0]
        assert finding["status"] == "confirmed"
        assert finding["severity"] == "MAJOR"
        audit_ids = {a["id"] for a in result["court_audit"]}
        assert "COURT-EVENT_ONCE-01" in audit_ids
        assert "COURT-UNIQUE-01" not in audit_ids
        # The head-only finding must survive the preexisting-defect rule
        # (method-scoped base exit 0 -> Base passed that method).
        audit = result["court_audit"][0]
        assert audit["final_status"] == "confirmed"
        assert audit.get("preexisting_check") is None

    def test_legacy_whole_run_ambiguous_still_produces_no_finding(self) -> None:
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [],
            "diff_results": [{
                "contract_id": "AUTH-01",
                "experiment_id": "DIFF-01",
                "verdict": "AMBIGUOUS",
                "detail": "Test fails in both Base and Head",
                "severity": "NONE",
                "confidence": 0.80,
                "evidence_type": "differential_execution",
                "base_exit_code": 1,
                "head_exit_code": 1,
            }],
            "contracts": [],
            "generated_tests_path": "",
        }
        result = run_review_court(cast(Phase0State, state))
        assert result["confirmed_findings"] == []

    def _ambiguous_both_entry(
        self, base_snippet: str, head_snippet: str
    ) -> dict[str, Any]:
        """A per-method both-sides-fail split entry (att-08 event test)."""
        return {
            "contract_id": "EVENT_ONCE-01",
            "experiment_id": "DIFF-01",
            "verdict": "AMBIGUOUS",
            "detail": (
                "Split differential: test method "
                "emailChangeEventMustGoToExpectedRoutingKey fails on both "
                "Base and Head — failure signatures compared by the Review "
                "Court for head-only attribution (whole-run exits: base 1, "
                "head 1)"
            ),
            "severity": None,
            "confidence": 0.65,
            "evidence_type": "differential_execution",
            "base_exit_code": 1,
            "head_exit_code": 1,
            "method_scoped": True,
            "failing_test_method": "emailChangeEventMustGoToExpectedRoutingKey",
            "base_method_status": "fail",
            "head_method_status": "fail",
            "whole_run_base_exit_code": 1,
            "whole_run_head_exit_code": 1,
            "base_output": base_snippet,
            "head_output": head_snippet,
            "base_db_snapshot": {},
            "head_db_snapshot": {},
            "db_state_verdict": "DB_CONSISTENT",
            "evidence_digest": "sha256:both-event",
        }

    def test_court_confirms_both_fail_with_distinct_head_failure(self) -> None:
        # att-08: the event test fails on Base because the unique inversion
        # kills the email-change precondition, and on Head because the
        # routing key is broken — a distinct head-only behavioral
        # difference must stay attributed to the head.
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [],
            "diff_results": [self._ambiguous_both_entry(
                base_snippet=(
                    "type=org.opentest4j.AssertionFailedError | "
                    "message=email change rejected ==> expected: <200> "
                    "but was: <400>"
                ),
                head_snippet=(
                    "type=org.opentest4j.AssertionFailedError | "
                    "message=routing key mismatch ==> expected event on "
                    "email.changed but none received"
                ),
            )],
            "contracts": [
                {"id": "EVENT_ONCE-01", "approved": True},
                {"id": "UNIQUE-01", "approved": True},
            ],
            "generated_tests_path": "capsules/tests/SpecProofGeneratedTest.java",
        }
        result = run_review_court(cast(Phase0State, state))
        confirmed_contracts = {
            str(f.get("contract_id")) for f in result["confirmed_findings"]
        }
        assert confirmed_contracts == {"EVENT_ONCE-01"}
        audit = result["court_audit"][0]
        assert audit["final_status"] == "confirmed"
        assert audit["preexisting_check"]["head_only_difference"] is True

    def test_court_downgrades_identical_both_fail(self) -> None:
        snippet = (
            "type=org.opentest4j.AssertionFailedError | "
            "message=same ==> expected: <a> but was: <b>"
        )
        state: dict[str, Any] = {
            "repo_path": "",
            "static_findings": [],
            "diff_results": [self._ambiguous_both_entry(snippet, snippet)],
            "contracts": [
                {"id": "EVENT_ONCE-01", "approved": True},
            ],
            "generated_tests_path": "capsules/tests/SpecProofGeneratedTest.java",
        }
        result = run_review_court(cast(Phase0State, state))
        assert result["confirmed_findings"] == []
        assert (
            result["candidate_findings"][0]["policy_outcome"]
            == "not_attributed"
        )
