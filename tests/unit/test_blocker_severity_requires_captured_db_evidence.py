"""#249 — the case-17 severity asymmetry, pinned in executable form.

A real four-case eval (#248) measured 4/4 detection PASS but
`Severity agreement: 66.7%`: case-21's AUTH-01 came out BLOCKER (as the golden
expects) while case-17's UNIQUE-01 came out **MAJOR** against a golden that
expects **BLOCKER**.

Tracing the severity chain showed this is NOT a mis-mapping:

* the spec's `## Expected Finding / Severity: BLOCKER` line is read by NO code
  (`grep` over `agent/` finds no severity parsing of the spec) — the finding's
  severity comes from the differential's captured evidence, not from the spec;
* `run_differential`'s combined-verdict path emits BLOCKER only when
  `db_verdict` is `DB_MUTATED_ON_UNAUTH` / `DB_MUTATED`, MAJOR otherwise;
* the Review Court's six-condition BLOCKER gate (ADR-004) then independently
  requires `db_state_verdict in {DB_MUTATED_ON_UNAUTH, DB_MUTATED}`
  (condition 4) AND confidence >= 0.90 (condition 6).

So case-17 caps at MAJOR because the generated uniqueness test FAILS its
assertion, and that failure rolls the transaction back: the H2 dumps are
identical on both sides (`DB_CONSISTENT`), so the persisted effect of the
regression is invisible to the very evidence the gate asks for. case-21
(permitAll) lets an unauthenticated write COMMIT, so its dumps differ.

These tests pin that rule so the asymmetry can never silently change, and keep
the two directions provable: "captured DB mutation + high confidence" still
earns BLOCKER, and "rollback hides the mutation" is capped.
"""
from __future__ import annotations

from typing import Any

from agent.nodes.run_differential import _compare_db_state
from agent.review_court.policy import (
    _check_blocker_conditions,
    policy_recalculate,
)


def _case17_candidate(**overrides: Any) -> dict[str, Any]:
    """A differential finding in exactly case-17's shape: the uniqueness test
    fails on Head and passes on Base, but the rolled-back transaction leaves
    identical DB dumps, and the differential's confidence is 0.88."""
    candidate: dict[str, Any] = {
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
        "location": "src/main/java/com/specproof/demo/UserService.java",
        "diff_result_index": 0,
        "base_exit_code": 0,
        "head_exit_code": 1,
    }
    candidate.update(overrides)
    return candidate


def _diff_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "experiment_id": "DIFF-01",
        "verdict": "REGRESSION",
        "evidence_type": "base_pass_head_fail",
        "base_exit_code": 0,
        "head_exit_code": 1,
        "db_state_verdict": "DB_CONSISTENT",
        "confidence": 0.88,
    }
    record.update(overrides)
    return record


_LOCATION = "src/main/java/com/specproof/demo/UserService.java"
_APPROVED = [{"id": "UNIQUE-01", "approved": True}]


def _court(candidate: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    return policy_recalculate(
        [candidate],
        model_output=None,
        contracts=_APPROVED,
        diff_results=[diff],
        generated_tests_path="reports/SpecProofGeneratedTest.java",
        changed_files=[_LOCATION],
    )


# ── condition 4/6: why case-17 cannot reach BLOCKER ────────────────


def test_rollback_hidden_mutation_cannot_earn_blocker() -> None:
    """case-17's shape: BLOCKER-eligible evidence type, but no captured DB
    mutation (identical dumps) and confidence 0.88 — so the six-condition gate
    refuses BLOCKER and the finding stays MAJOR."""
    candidate = _case17_candidate()
    diff = _diff_record()

    conditions = _check_blocker_conditions(
        candidate, _APPROVED, [diff], "reports/SpecProofGeneratedTest.java", [_LOCATION],
    )

    # The decisive two, stated individually so a future change names which one
    # it relaxes rather than quietly flipping the whole verdict.
    assert conditions["blocker_conditions"]["2_base_head_execution"] is True, (
        "base_pass_head_fail with exit codes IS real execution evidence"
    )
    assert conditions["blocker_conditions"]["4_db_behavior_evidence"] is False, (
        "the rolled-back transaction leaves identical DB dumps — the gate "
        "correctly refuses to call that captured DB evidence"
    )
    assert conditions["blocker_conditions"]["6_confidence_090"] is False, (
        "the differential's regression confidence is 0.88, below the 0.90 floor"
    )
    assert conditions["all_blocker_conditions_met"] is False

    # And end to end: a BLOCKER-labelled candidate is capped, not passed through.
    capped = _court(_case17_candidate(severity="BLOCKER"), _diff_record())
    confirmed = capped["confirmed_findings"]
    assert len(confirmed) == 1
    assert confirmed[0]["severity"] == "MAJOR", (
        "a BLOCKER missing gate conditions must be capped to MAJOR, not shown "
        "to the reviewer as BLOCKER"
    )


def test_captured_db_mutation_with_high_confidence_still_earns_blocker() -> None:
    """The control — case-21's shape: the unauthenticated write commits, so the
    users-table dumps differ and confidence clears 0.90. BLOCKER survives."""
    candidate = _case17_candidate(
        contract_id="AUTH-01",
        severity="BLOCKER",
        confidence=0.95,
        db_state_verdict="DB_MUTATED_ON_UNAUTH",
        location=_LOCATION,
    )
    diff = _diff_record(db_state_verdict="DB_MUTATED_ON_UNAUTH", confidence=0.95)

    conditions = _check_blocker_conditions(
        candidate,
        [{"id": "AUTH-01", "approved": True}],
        [diff],
        "reports/SpecProofGeneratedTest.java",
        [_LOCATION],
    )

    assert conditions["blocker_conditions"]["4_db_behavior_evidence"] is True
    assert conditions["blocker_conditions"]["6_confidence_090"] is True
    assert conditions["all_blocker_conditions_met"] is True

    result = policy_recalculate(
        [candidate],
        model_output=None,
        contracts=[{"id": "AUTH-01", "approved": True}],
        diff_results=[diff],
        generated_tests_path="reports/SpecProofGeneratedTest.java",
        changed_files=[_LOCATION],
    )
    confirmed = result["confirmed_findings"]
    assert len(confirmed) == 1
    assert confirmed[0]["severity"] == "BLOCKER"


# ── the DB snapshot side that the gate reads ───────────────────────


def test_db_state_comparison_maps_the_two_mutation_shapes_and_the_rollback() -> None:
    """`_compare_db_state` is the only producer of condition 4's evidence, so
    its mapping is pinned: users differs -> DB_MUTATED_ON_UNAUTH, any other
    table differs -> DB_MUTATED, identical -> DB_CONSISTENT (case-17's rollback),
    no dump -> DB_NO_EVIDENCE (never silently treated as 'no mutation')."""
    snap = {"method": "h2_file_dump", "rows": {"users:1": "a@x"}}

    assert _compare_db_state(snap, {**snap, "rows": {"users:1": "b@x"}})[0] == (
        "DB_MUTATED_ON_UNAUTH"
    )
    # users must be IDENTICAL here: the loop checks users first, so a users
    # difference would win and report ON_UNAUTH. Only ORDERS differs.
    assert _compare_db_state(
        snap, {"method": "h2_file_dump", "rows": {"users:1": "a@x", "orders:1": "new"}}
    )[0] == "DB_MUTATED"
    assert _compare_db_state(snap, snap)[0] == "DB_CONSISTENT"
    # An empty row set on one side is a real difference, not a no-op.
    assert _compare_db_state(snap, {"method": "h2_file_dump", "rows": {}})[0] != (
        "DB_CONSISTENT"
    )

    no_dump = {"method": "none", "rows": {}, "note": "H2 jar not found"}
    verdict, detail = _compare_db_state(no_dump, no_dump)
    assert verdict == "DB_NO_EVIDENCE"
    assert "H2 jar not found" in detail, "the capability gap must reach the reader"
