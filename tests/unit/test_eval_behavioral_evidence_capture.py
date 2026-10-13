"""#250 — behavioral evidence capture for the rollback-hidden regression.

These tests pin the *capture* half of the #250 evidence gap: a behavioral
regression (http_verdict == REGRESSION) whose DB effect was rolled back by the
failing head-side generated test lands as DB_CONSISTENT, and ADR-004 condition 4
(db_behavior_evidence) therefore cannot be met. The helper records that signal
in machine-readable form so reviewers/UI can see *why* no DB mutation was
captured, instead of reading it as "no regression happened".

This is capture-only. It must NOT change severity, confidence, or the ADR-004
gate (the honest BLOCKER route is in-flight DB-state capture, a separate,
design-reviewed step — not raising confidence to 0.90 to force BLOCKER).
"""

from agent.nodes.run_differential import _behavioral_evidence


def test_case17_shape_rollback_hidden_regression_is_captured():
    """case-17: head test fails -> txn rolls back -> DB_CONSISTENT.

    The regression (duplicate email accepted) is real and behavioral, but its
    persistence was rolled back by the failing generated test. The helper must
    flag exactly this so the MAJOR cap is understood, not mistaken for a miss.
    """
    ev = _behavioral_evidence(
        verdict="REGRESSION",
        db_verdict="DB_CONSISTENT",
        base_status="pass",
        head_status="fail",
        failing_method="testUniqueEmailRejected",
    )
    assert ev["captured"] is True
    assert ev["head_test_failed"] is True
    assert ev["db_effect_rolled_back"] is True
    assert ev["failing_method"] == "testUniqueEmailRejected"
    assert "rolled the transaction back" in ev["note"]
    assert "MAJOR" in ev["note"]


def test_case21_shape_unauth_write_committed_is_not_rolled_back():
    """case-21: permitAll removed -> unauth write commits -> DB_MUTATED_ON_UNAUTH.

    Here the DB mutation IS captured, so this is NOT the rollback-hidden case.
    The helper must not flag db_effect_rolled_back.
    """
    ev = _behavioral_evidence(
        verdict="REGRESSION",
        db_verdict="DB_MUTATED_ON_UNAUTH",
        base_status="pass",
        head_status="fail",
        failing_method="testUnauthenticatedWriteRejected",
    )
    assert ev["captured"] is True
    assert ev["db_effect_rolled_back"] is False
    assert ev["head_test_failed"] is True
    assert "captured DB mutation" in ev["note"]


def test_non_users_table_mutation_is_not_rolled_back():
    """REGRESSION with DB_MUTATED (orders/products) is also a captured mutation."""
    ev = _behavioral_evidence(
        verdict="REGRESSION",
        db_verdict="DB_MUTATED",
        base_status="pass",
        head_status="fail",
        failing_method="testOrderTotalEnforced",
    )
    assert ev["db_effect_rolled_back"] is False
    assert ev["captured"] is True


def test_compliant_run_captures_nothing():
    ev = _behavioral_evidence(
        verdict="COMPLIANT",
        db_verdict="DB_CONSISTENT",
        base_status="pass",
        head_status="pass",
    )
    assert ev["captured"] is False
    assert ev["head_test_failed"] is False
    assert ev["db_effect_rolled_back"] is False
    assert ev["failing_method"] is None
    assert "No behavioral regression" in ev["note"]


def test_ambiguous_both_fail_is_not_a_captured_regression():
    ev = _behavioral_evidence(
        verdict="AMBIGUOUS",
        db_verdict="DB_CONSISTENT",
        base_status="fail",
        head_status="fail",
        failing_method="testSomething",
    )
    assert ev["captured"] is False
    # head_test_failed requires base PASS; both-fail is not a head regression.
    assert ev["head_test_failed"] is False
    assert ev["db_effect_rolled_back"] is False


def test_shape_is_stable_additive_metadata_only():
    """The helper returns a fixed, additive metadata dict.

    Pinning the key set catches anyone who silently repurposes this field to
    carry severity/confidence (the ADR-004 bypass we must never take).
    """
    ev = _behavioral_evidence("REGRESSION", "DB_CONSISTENT", "pass", "fail", "m")
    assert set(ev.keys()) == {
        "captured",
        "head_test_failed",
        "db_effect_rolled_back",
        "failing_method",
        "note",
    }
    # No severity / confidence / gate fields leak in here.
    assert "severity" not in ev
    assert "confidence" not in ev
