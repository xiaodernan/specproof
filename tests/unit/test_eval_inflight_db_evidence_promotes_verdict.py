"""#254b - the scaffold-wiped DB verdict is promoted to a captured-mutation
verdict ONLY when the in-flight signal proves a head-only DB violation.

#253 proved case-17's regression commits the duplicate email but a later
@BeforeEach deleteAll wipes the row before the post-run H2 dump, so the dump
reads DB_CONSISTENT. The generated test's own DB-invariant assertion still fires
in-flight (head_only=True via _db_violation_evidence). This module pins the
pure promotion rule so the BLOCKER gate (ADR-004 condition 4) can fire honestly
for case-17 - and so the promotion can never silently widen to cases that lack
in-flight evidence.
"""
from agent.nodes.run_differential import _apply_inflight_db_evidence

CONSISTENT = "Post-run dumps identical"
NO_EVIDENCE = "no dump captured"


def test_consistent_plus_head_only_becomes_mutation():
    verdict, detail = _apply_inflight_db_evidence(
        "DB_CONSISTENT", CONSISTENT, True
    )
    assert verdict == "DB_MUTATED_ON_UNAUTH"
    assert "DB STATE VIOLATION" in detail
    assert "@BeforeEach deleteAll" in detail


def test_consistent_without_head_only_stays_consistent():
    verdict, detail = _apply_inflight_db_evidence(
        "DB_CONSISTENT", CONSISTENT, False
    )
    assert verdict == "DB_CONSISTENT"
    assert detail == CONSISTENT


def test_already_mutated_is_idempotent():
    verdict, detail = _apply_inflight_db_evidence(
        "DB_MUTATED_ON_UNAUTH", "users table differs", True
    )
    assert verdict == "DB_MUTATED_ON_UNAUTH"
    assert detail == "users table differs"


def test_no_dump_is_never_promoted_even_with_head_only():
    # #249 discipline: absence of a dump is not evidence of no mutation, so a
    # DB_NO_EVIDENCE verdict must NOT be promoted just because the head test
    # observed a violation.
    verdict, detail = _apply_inflight_db_evidence(
        "DB_NO_EVIDENCE", NO_EVIDENCE, True
    )
    assert verdict == "DB_NO_EVIDENCE"
    assert detail == NO_EVIDENCE


def test_promotion_does_not_invent_severity_or_confidence():
    verdict, detail = _apply_inflight_db_evidence(
        "DB_CONSISTENT", CONSISTENT, True
    )
    # The promotion is a verdict-category change, not a verdict/severity object.
    # It must not smuggle severity/confidence into the returned pair.
    assert isinstance(verdict, str)
    assert isinstance(detail, str)
    assert "BLOCKER" not in detail or "promoted" in detail  # detail is prose
