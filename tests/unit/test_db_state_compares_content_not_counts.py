"""`_compare_db_state` must compare CONTENT, not row counts.

This is the factual foundation of the #250 evidence-capture question. The
case-17 regression ("a duplicate email change was accepted") changes a row's
*content* while leaving the row count identical; the BLOCKER path asks the DB
snapshot for exactly that captured mutation. If the comparison were ever
weakened to a row-count comparison, that regression would silently lose its
evidence and read as `DB_CONSISTENT` -> MAJOR, which is the "假绿" shape.

The snapshots use the exact shape `_capture_db_snapshot` produces: the H2 dump
prints ``users:1=a@x.com`` lines, which the node splits on the first ``=`` into
``rows = {"users:1": "a@x.com"}``.
"""
from __future__ import annotations

from typing import Any

from agent.nodes.run_differential import _compare_db_state

_BASE_USERS = {"users:1": "specproof@example.com", "users:2": "bob@example.com"}


def _snapshot(rows: dict[str, str], method: str = "h2_file_dump") -> dict[str, Any]:
    return {"method": method, "rows": dict(rows), "note": ""}


def test_a_changed_cell_detected_even_when_the_row_count_is_identical() -> None:
    """The case-17 shape: content changed, count unchanged, still detected."""
    base = _snapshot({"users:1": "specproof@example.com", "users:2": "bob@example.com"})
    head = _snapshot({"users:1": "specproof@example.com", "users:2": "alice@example.com"})
    verdict, detail = _compare_db_state(base, head)
    assert verdict == "DB_MUTATED_ON_UNAUTH", detail
    assert "row" in detail, detail
    assert "alice@example.com" in detail, detail


def test_a_users_row_count_change_is_detected() -> None:
    base = _snapshot({"users:1": "a@x.com"})
    head = _snapshot({"users:1": "a@x.com", "users:2": "b@x.com"})
    verdict, detail = _compare_db_state(base, head)
    assert verdict == "DB_MUTATED_ON_UNAUTH", detail


def test_a_changed_non_users_cell_is_db_mutated() -> None:
    base = _snapshot({"users:1": "a@x.com", "products:7": "5:0"})
    head = _snapshot({"users:1": "a@x.com", "products:7": "4:1"})
    verdict, detail = _compare_db_state(base, head)
    assert verdict == "DB_MUTATED", detail


def test_identical_dumps_are_db_consistent() -> None:
    verdict, detail = _compare_db_state(_snapshot(_BASE_USERS), _snapshot(_BASE_USERS))
    assert verdict == "DB_CONSISTENT", detail


def test_a_users_difference_outranks_a_products_difference() -> None:
    """users is the flagship evidence path; its verdict name is policy."""
    base = _snapshot({"users:1": "a@x.com", "products:1": "5:0"})
    head = _snapshot({"users:1": "b@x.com", "products:1": "4:1"})
    verdict, _detail = _compare_db_state(base, head)
    assert verdict == "DB_MUTATED_ON_UNAUTH"


def test_a_missing_dump_is_not_db_consistent() -> None:
    """No evidence must never read as "the DBs agree"."""
    dumped = _snapshot(_BASE_USERS)
    undumped = {"method": "none", "rows": {}, "note": "No file-based H2 database found."}
    verdict, detail = _compare_db_state(dumped, undumped)
    assert verdict == "DB_NO_EVIDENCE", detail
    assert "DB_CONSISTENT" not in detail


def test_an_absent_table_on_both_sides_is_not_a_difference() -> None:
    """A table neither ref materialised must not manufacture a mutation."""
    base = _snapshot({"users:1": "a@x.com"})
    head = _snapshot({"users:1": "a@x.com"})
    verdict, detail = _compare_db_state(base, head)
    assert verdict == "DB_CONSISTENT", detail
