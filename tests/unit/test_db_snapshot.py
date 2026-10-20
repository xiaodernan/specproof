"""Unified DB state snapshot tests (Phase 3, P3-5).

The module exists because the comparison used to carry a HARDCODED table
list::

    for table in ("users", "products", "orders"):

which meant a domain nobody listed was invisible to the comparison — a
real difference reported as "the dumps are identical". These tests pin
the table-agnostic behaviour, and the compatibility promise to every
consumer that already reads the flat ``rows`` map.

No database, no Docker: the snapshots are constructed in memory.
"""

from __future__ import annotations

from typing import Any

import pytest

from experiments.db_snapshot import (
    DIFF_ADDED,
    DIFF_CHANGED,
    DIFF_REMOVED,
    METHOD_H2_FILE_DUMP,
    METHOD_NONE,
    DbSnapshot,
    compare_snapshots,
    differences_to_dicts,
    parse_dump_rows,
)


def _snapshot(rows: dict[str, str], *, method: str = METHOD_H2_FILE_DUMP) -> DbSnapshot:
    return DbSnapshot(method=method, tables=parse_dump_rows(rows))


# ── the parser ─────────────────────────────────────────────────────────────


class TestParseDumpRows:
    def test_rows_are_split_by_table(self) -> None:
        tables = parse_dump_rows({
            "users:1": "a@x",
            "users:2": "b@x",
            "orders:7": "u1:r1:100",
        })
        assert set(tables) == {"users", "orders"}
        assert tables["users"].rows == {"1": "a@x", "2": "b@x"}
        assert tables["orders"].rows == {"7": "u1:r1:100"}

    def test_a_row_without_a_table_prefix_is_kept_not_dropped(self) -> None:
        """Losing a row would be losing evidence."""
        tables = parse_dump_rows({"orphanrow": "value"})
        assert "_unattributed" in tables
        assert tables["_unattributed"].rows == {"orphanrow": "value"}

    def test_the_first_separator_wins(self) -> None:
        """A table name or a row value may contain the other separator."""
        tables = parse_dump_rows({"weird:key:with:colons": "a=b=c"})
        assert "weird" in tables
        assert tables["weird"].rows == {"key:with:colons": "a=b=c"}

    def test_empty_input_gives_no_tables(self) -> None:
        assert parse_dump_rows({}) == {}


# ── the snapshot model ─────────────────────────────────────────────────────


class TestSnapshotModel:
    def test_no_evidence_is_not_an_empty_database(self) -> None:
        assert DbSnapshot.none("no dump").has_evidence() is False
        assert _snapshot({"users:1": "a"}).has_evidence() is True

    def test_table_names_are_sorted(self) -> None:
        snapshot = _snapshot({"z:1": "v", "a:1": "v", "m:1": "v"})
        assert snapshot.table_names() == ["a", "m", "z"]

    def test_flat_rows_reproduces_the_legacy_format(self) -> None:
        """Every existing consumer reads snapshot["rows"] — it must match."""
        legacy = {"users:1": "a@x", "orders:7": "u1:r1:100"}
        snapshot = _snapshot(legacy)
        assert snapshot.flat_rows() == legacy

    def test_to_dict_keeps_the_legacy_keys(self) -> None:
        payload = _snapshot({"users:1": "a@x"}).to_dict()
        assert payload["method"] == METHOD_H2_FILE_DUMP
        assert payload["rows"] == {"users:1": "a@x"}
        assert "note" in payload
        # AND the new per-table breakdown.
        assert payload["tables"]["users"]["rows"] == {"1": "a@x"}

    def test_from_dict_reads_the_legacy_wire_form(self) -> None:
        legacy = {"method": METHOD_H2_FILE_DUMP, "rows": {"users:1": "a@x"}, "note": ""}
        snapshot = DbSnapshot.from_dict(legacy)
        assert snapshot.has_evidence() is True
        assert snapshot.table("users") is not None
        assert snapshot.table("users").rows == {"1": "a@x"}  # type: ignore[union-attr]

    def test_from_dict_reads_the_new_wire_form(self) -> None:
        payload = _snapshot({"users:1": "a@x"}).to_dict()
        snapshot = DbSnapshot.from_dict(payload)
        assert snapshot.flat_rows() == {"users:1": "a@x"}

    def test_from_dict_of_garbage_is_no_evidence(self) -> None:
        assert DbSnapshot.from_dict({}).has_evidence() is False
        assert DbSnapshot.from_dict("not a mapping").has_evidence() is False  # type: ignore[arg-type]

    def test_round_trip_is_stable(self) -> None:
        original = _snapshot({"users:1": "a@x", "orders:7": "u1:r1:100"})
        restored = DbSnapshot.from_dict(original.to_dict())
        assert restored.to_dict() == original.to_dict()


# ── the table-agnostic comparison ──────────────────────────────────────────


class TestComparison:
    def test_identical_snapshots_have_no_differences(self) -> None:
        snapshot = _snapshot({"users:1": "a@x"})
        assert compare_snapshots(snapshot, snapshot) == []

    def test_a_changed_row_is_reported(self) -> None:
        base = _snapshot({"users:1": "a@x"})
        head = _snapshot({"users:1": "b@x"})
        differences = compare_snapshots(base, head)
        assert len(differences) == 1
        assert differences[0].table == "users"
        assert differences[0].kind == DIFF_CHANGED
        assert "a@x" in differences[0].detail
        assert "b@x" in differences[0].detail

    def test_a_table_nobody_listed_is_still_compared(self) -> None:
        """The P3-5 point: the comparison discovers the tables.

        Before this module a domain that was not in the hardcoded list
        was invisible — the dumps differed and the verdict said
        "identical".
        """
        base = _snapshot({"audit:1": "x"})
        head = _snapshot({"audit:1": "y"})
        differences = compare_snapshots(base, head)
        assert len(differences) == 1
        assert differences[0].table == "audit"

    def test_an_appeared_table_is_reported(self) -> None:
        base = _snapshot({"users:1": "a@x"})
        head = _snapshot({"users:1": "a@x", "audit:1": "new"})
        differences = compare_snapshots(base, head)
        assert differences[0].table == "audit"
        assert differences[0].kind == DIFF_ADDED

    def test_a_disappeared_table_is_reported(self) -> None:
        base = _snapshot({"users:1": "a@x", "audit:1": "x"})
        head = _snapshot({"users:1": "a@x"})
        differences = compare_snapshots(base, head)
        assert differences[0].table == "audit"
        assert differences[0].kind == DIFF_REMOVED

    def test_missing_evidence_yields_no_differences(self) -> None:
        """No dump is not evidence of a difference — and not of sameness."""
        base = _snapshot({"users:1": "a@x"})
        none = DbSnapshot.none("H2 jar not found")
        assert compare_snapshots(base, none) == []
        assert compare_snapshots(none, none) == []

    def test_an_empty_table_on_both_sides_is_not_a_difference(self) -> None:
        base = _snapshot({})
        head = _snapshot({})
        assert compare_snapshots(base, head) == []

    def test_differences_are_in_table_order(self) -> None:
        base = _snapshot({"z:1": "a", "a:1": "a"})
        head = _snapshot({"z:1": "b", "a:1": "b"})
        differences = compare_snapshots(base, head)
        assert [d.table for d in differences] == ["a", "z"]

    def test_differences_are_json_ready(self) -> None:
        base = _snapshot({"users:1": "a@x"})
        head = _snapshot({"users:1": "b@x"})
        payload = differences_to_dicts(compare_snapshots(base, head))
        assert payload[0]["table"] == "users"
        assert payload[0]["kind"] == DIFF_CHANGED


# ── the policy layer keeps its verdict names ──────────────────────────────


class TestPolicyStaysOutside:
    def test_the_node_maps_users_to_the_unauth_evidence(self) -> None:
        """The COMPARISON is table-agnostic; the VERDICT NAME is policy."""
        from agent.nodes.run_differential import _compare_db_state

        snap = {"method": METHOD_H2_FILE_DUMP, "rows": {"users:1": "a@x"}}
        verdict, _detail = _compare_db_state(
            snap, {**snap, "rows": {"users:1": "b@x"}}
        )
        assert verdict == "DB_MUTATED_ON_UNAUTH"

    def test_the_node_maps_any_other_table_to_the_general_evidence(self) -> None:
        from agent.nodes.run_differential import _compare_db_state

        snap = {"method": METHOD_H2_FILE_DUMP, "rows": {"users:1": "a@x"}}
        verdict, _detail = _compare_db_state(
            snap,
            {"method": METHOD_H2_FILE_DUMP,
             "rows": {"users:1": "a@x", "orders:1": "new"}},
        )
        assert verdict == "DB_MUTATED"

    def test_a_table_outside_the_old_hardcoded_list_is_no_longer_invisible(
        self,
    ) -> None:
        """The regression this module removes: an unlisted table's
        difference used to be reported as "the dumps are identical"."""
        from agent.nodes.run_differential import _compare_db_state

        snap = {"method": METHOD_H2_FILE_DUMP, "rows": {"audit:1": "x"}}
        verdict, _detail = _compare_db_state(
            snap, {**snap, "rows": {"audit:1": "y"}}
        )
        assert verdict == "DB_MUTATED"
        assert verdict != "DB_CONSISTENT"

    def test_no_dump_is_still_no_evidence(self) -> None:
        from agent.nodes.run_differential import _compare_db_state

        no_dump = {"method": METHOD_NONE, "rows": {}, "note": "H2 jar not found"}
        verdict, detail = _compare_db_state(no_dump, no_dump)
        assert verdict == "DB_NO_EVIDENCE"
        assert "H2 jar not found" in detail


@pytest.mark.parametrize("payload", [{}, {"rows": {}}, {"method": METHOD_NONE}])
def test_a_snapshot_without_a_dump_never_claims_evidence(payload: dict[str, Any]) -> None:
    assert DbSnapshot.from_dict(payload).has_evidence() is False
