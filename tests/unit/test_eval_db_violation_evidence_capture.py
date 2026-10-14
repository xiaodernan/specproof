"""#254 - in-flight DB-violation evidence is captured from the generated test's
own failure text, independent of the post-run H2 dump.

#253 proved case-17's persisted mutation is wiped by a later @BeforeEach
deleteAll before the differential's DB dump is taken, so the dump reads
DB_CONSISTENT even though the mutation was committed. The generated test's
DB-invariant assertion fires at the moment it OBSERVES the mutated row and its
message carries the "DB STATE VIOLATION" marker - in-flight evidence the dump
cannot see. This test pins the pure extractor that turns that marker into a
structured signal, and asserts it does NOT carry severity/confidence (so the
ADR-004 gate is not bypassed by this capture).
"""

from agent.nodes.run_differential import _db_violation_evidence

MARKER = "DB STATE VIOLATION"


def test_head_only_violation_is_flagged_head_only():
    head = "duplicateEmailChangeMustBeRejected FAILED: " + MARKER + \
           ": duplicate email change was accepted and persisted"
    ev = _db_violation_evidence("", head)
    assert ev["head_observed"] is True
    assert ev["base_observed"] is False
    assert ev["head_only"] is True


def test_base_and_head_both_violate_is_not_head_only():
    text = MARKER + ": blank email change was accepted and persisted"
    ev = _db_violation_evidence(text, text)
    assert ev["head_observed"] is True
    assert ev["base_observed"] is True
    assert ev["head_only"] is False


def test_no_violation_yields_all_false():
    ev = _db_violation_evidence("all good", "all good too")
    assert ev["head_observed"] is False
    assert ev["base_observed"] is False
    assert ev["head_only"] is False


def test_empty_inputs_do_not_raise():
    ev = _db_violation_evidence(None, None)
    assert ev["head_observed"] is False
    assert ev["base_observed"] is False
    assert ev["head_only"] is False


def test_capture_is_honest_does_not_carve_severity_or_confidence():
    ev = _db_violation_evidence("", MARKER + ": persisted")
    # The capture is a raw observation signal, not a verdict. It must not
    # smuggle severity/confidence into the entry - the BLOCKER wiring is a
    # separate, design-reviewed step (#254), not a confidence bump here.
    assert "severity" not in ev
    assert "confidence" not in ev
    assert ev["marker"] == MARKER
