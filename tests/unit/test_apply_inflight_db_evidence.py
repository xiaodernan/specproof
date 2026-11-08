"""Direct tests for _apply_inflight_db_evidence (#253/#254b): the
idempotent promotion of a scaffold-wiped DB mutation to a captured-mutation
verdict.

A head-side generated test can observe a mutated row (DB STATE VIOLATION
marker in its failure text) while a later @BeforeEach deleteAll() wipes it
before the post-run H2 dump, so the dump reads DB_CONSISTENT even though
the regression committed. When only the head side saw the violation, the
in-flight assertion is promoted to DB_MUTATED_ON_UNAUTH so BLOCKER can
fire honestly.

Rules pinned here:
- DB_CONSISTENT + head-only violation -> promoted to DB_MUTATED_ON_UNAUTH.
- DB_CONSISTENT without head-only violation -> untouched.
- DB_NO_EVIDENCE (no dump at all) -> never promoted (absence of a dump is
  not evidence of no mutation).
- Already-mutated verdicts -> untouched (idempotent).
"""

from __future__ import annotations

from agent.nodes.run_differential import _apply_inflight_db_evidence

DB_CONSISTENT = ("DB_CONSISTENT", "Base and Head DB dumps are identical")
DB_NO_EVIDENCE = ("DB_NO_EVIDENCE", "No H2 dump available: collector unreachable")
DB_MUTATED = ("DB_MUTATED", "products table differs")
DB_MUTATED_ON_UNAUTH = ("DB_MUTATED_ON_UNAUTH", "users table differs")


def test_consistent_dump_with_head_only_violation_is_promoted() -> None:
    verdict, detail = _apply_inflight_db_evidence(*DB_CONSISTENT, True)
    assert verdict == "DB_MUTATED_ON_UNAUTH"
    assert "head-side generated test observed a DB-state violation" in detail
    assert "wiped by a later test's @BeforeEach deleteAll" in detail
    assert "ADR-004 condition 4" in detail


def test_consistent_dump_without_violation_stays_consistent() -> None:
    verdict, detail = _apply_inflight_db_evidence(*DB_CONSISTENT, False)
    assert verdict == "DB_CONSISTENT"
    assert detail == DB_CONSISTENT[1]


def test_no_evidence_is_never_promoted_even_with_violation() -> None:
    """The absence of a dump is not evidence of no mutation (#249)."""
    verdict, detail = _apply_inflight_db_evidence(*DB_NO_EVIDENCE, True)
    assert verdict == "DB_NO_EVIDENCE"
    assert detail == DB_NO_EVIDENCE[1]


def test_already_mutated_verdict_is_idempotent() -> None:
    verdict, detail = _apply_inflight_db_evidence(*DB_MUTATED, True)
    assert verdict == "DB_MUTATED"
    assert detail == DB_MUTATED[1]


def test_already_promoted_verdict_stays_promoted() -> None:
    verdict, detail = _apply_inflight_db_evidence(*DB_MUTATED_ON_UNAUTH, True)
    assert verdict == "DB_MUTATED_ON_UNAUTH"
    assert detail == DB_MUTATED_ON_UNAUTH[1]
