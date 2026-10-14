"""#254b closure at the Review Court level - Maven-free proof.

The live case-17 run (#254c) is BLOCKED in this environment: Docker is not
available, so the spring-backend Maven differential cannot run and the
specproof-maven-cache-1000 volume cannot be re-seeded. This test proves the
half of the #254b loop that does NOT need Maven:

  run_differential emits (via _apply_inflight_db_evidence) a diff_result with
  db_state_verdict == DB_MUTATED_ON_UNAUTH and confidence 0.95 for the
  scaffold-wiped case-17 shape. Given exactly that diff_result, the Review
  Court (policy_recalculate / ADR-004) must confirm BLOCKER - matching
  golden-cases/case-17-logic-inversion/ground-truth.json expected_severity.

Combined with test_eval_inflight_db_evidence_promotes_verdict.py (which proves
run_differential produces that diff_result), this closes the #248/#249
severity-asymmetry loop without a Docker run. When Docker returns, #254c should
re-run the live case-17 eval to confirm the surefire failure text actually
carries the DB STATE VIOLATION marker.
"""
from pathlib import Path

from agent.review_court.policy import policy_recalculate

_LOCATION = "src/main/java/com/specproof/demo/UserService.java"
_APPROVED = [{"id": "UNIQUE-01", "approved": True}]


def _court(candidate: dict, diff: dict) -> dict:
    return policy_recalculate(
        [candidate],
        model_output=None,
        contracts=_APPROVED,
        diff_results=[diff],
        generated_tests_path="reports/SpecProofGeneratedTest.java",
        changed_files=[_LOCATION],
    )


def test_case17_uniq01_with_promoted_db_verdict_earns_blocker() -> None:
    """The exact candidate shape run_differential now emits for case-17: because
    #254b promotes db_state_verdict to DB_MUTATED_ON_UNAUTH, the combined-verdict
    BLOCKER branch (run_differential.py:539) sets combined_severity=BLOCKER and
    confidence=0.95. That BLOCKER candidate - with db_state_verdict in the
    mutation set - must be CONFIRMED by the court (ADR-004 condition 4 now truly
    holds), matching the golden's expected_severity BLOCKER.

    NOTE (court contract, policy.py:606): the court only DOWNGRADES a proposed
    BLOCKER; it never promotes MAJOR->BLOCKER. So the BLOCKER trigger is
    run_differential emitting severity=BLOCKER, which #254b's promotion enables.
    """
    candidate = {
        "id": "DIFF-UNIQUE-01",
        "contract_id": "UNIQUE-01",
        "severity": "BLOCKER",  # run_differential emits this after the promotion
        "type": "guard_negated",
        "description": "duplicate-email guard inverted: duplicates accepted",
        "evidence_type": "base_pass_head_fail",
        "confidence": 0.95,
        "source": "differential",
        "status": "candidate",
        "diff_verdict": "REGRESSION",
        "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
        "location": _LOCATION,
        "base_exit_code": 0,
        "head_exit_code": 1,
    }
    diff = {
        "experiment_id": "DIFF-01",
        "verdict": "REGRESSION",
        "evidence_type": "base_pass_head_fail",
        "base_exit_code": 0,
        "head_exit_code": 1,
        "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
        "confidence": 0.95,
    }

    result = _court(candidate, diff)
    confirmed = result["confirmed_findings"]
    assert len(confirmed) == 1
    assert confirmed[0]["contract_id"] == "UNIQUE-01"
    assert confirmed[0]["severity"] == "BLOCKER"

    golden = __import__("json").loads(
        Path("golden-cases/case-17-logic-inversion/ground-truth.json").read_text(
            encoding="utf-8"
        )
    )
    assert golden["expected_severity"] == "BLOCKER"
    assert confirmed[0]["severity"] == golden["expected_severity"]


def test_case17_without_promotion_stays_major_not_blocker() -> None:
    """Court contract (policy.py:606): the court never promotes a MAJOR candidate
    to BLOCKER, no matter how strong the evidence. BLOCKER is only ever PROPOSED
    by run_differential; the court only gates it. So a pre-#254b candidate
    (db_state_verdict still DB_CONSISTENT, confidence 0.88, severity MAJOR) stays
    MAJOR - confirming the promotion is the actual trigger, not the court."""
    candidate = {
        "id": "DIFF-UNIQUE-01",
        "contract_id": "UNIQUE-01",
        "severity": "MAJOR",
        "type": "guard_negated",
        "description": "duplicate-email guard inverted: duplicates accepted",
        "evidence_type": "base_pass_head_fail",
        "confidence": 0.88,
        "source": "differential",
        "status": "candidate",
        "diff_verdict": "REGRESSION",
        "db_state_verdict": "DB_CONSISTENT",
        "location": _LOCATION,
        "base_exit_code": 0,
        "head_exit_code": 1,
    }
    diff = {
        "experiment_id": "DIFF-01",
        "verdict": "REGRESSION",
        "evidence_type": "base_pass_head_fail",
        "base_exit_code": 0,
        "head_exit_code": 1,
        "db_state_verdict": "DB_CONSISTENT",
        "confidence": 0.88,
    }

    result = _court(candidate, diff)
    confirmed = result["confirmed_findings"]
    assert len(confirmed) == 1
    assert confirmed[0]["severity"] == "MAJOR"
