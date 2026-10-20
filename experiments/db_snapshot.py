"""Unified database state snapshots (Phase 3, P3-5).

The roadmap's wording: "统一三表或多表 H2/Testcontainers 状态快照，
避免每个案例各写一套解析。"

Before this module the state capture lived inside one node as a private
function with a HARDCODED table list::

    for table in ("users", "products", "orders"):

Every new demo domain meant editing the comparison code, every experiment
wrote its own parser, and the snapshot wire format was a flat map with
"table:rowid" prefixes that each consumer re-parsed by hand.

This module is the one place that knows how a database state is
represented:

* ``DbSnapshot`` — a structured snapshot with PER-TABLE rows. It can
  still emit the legacy flat ``rows`` map, so every existing consumer
  keeps working untouched.
* ``parse_dump_rows`` — one parser for the ``table:rowid=value`` dump
  format the collectors produce.
* ``compare_snapshots`` — a TABLE-AGNOSTIC comparison. It discovers the
  tables from the two snapshots instead of a hardcoded list, and returns
  the differences; it does NOT decide what a difference MEANS.

That last point is the important one. "the users table changed" is an
observation; "a users-table change is a BLOCKER" is POLICY, and policy
belongs to the Review Court, not to the comparison layer. A snapshot
module that hardcoded the table list silently decided policy by omission
— a domain nobody listed would have been invisible to the comparison.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

#: The dump format the collectors emit: "<table>:<row id>=<row value>".
#: Both separators are the FIRST occurrence — a table name or a row value
#: may itself contain the other character.
TABLE_PREFIX_SEPARATOR = ":"
ROW_VALUE_SEPARATOR = "="

#: Snapshot method names. "none" means no evidence was captured — never a
#: clean run.
METHOD_NONE = "none"
METHOD_H2_FILE_DUMP = "h2_file_dump"
METHOD_TESTCONTAINERS = "testcontainers"

#: Difference kinds.
DIFF_CHANGED = "changed"
DIFF_ADDED = "added"
DIFF_REMOVED = "removed"


@dataclass(frozen=True)
class TableSnapshot:
    """One table's observed rows: row id → row value."""

    table: str
    rows: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.rows

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "rows": dict(self.rows)}


@dataclass(frozen=True)
class DbSnapshot:
    """The observed state of a database, per table."""

    method: str = METHOD_NONE
    tables: dict[str, TableSnapshot] = field(default_factory=dict)
    note: str = ""
    source: str = ""

    def has_evidence(self) -> bool:
        """True when a dump was actually captured.

        "No dump" is not "an empty database": an empty database and a
        missing dump are different observations, and only the first is
        evidence.
        """
        return self.method != METHOD_NONE

    def table_names(self) -> list[str]:
        """Every table present, sorted (deterministic)."""
        return sorted(self.tables)

    def table(self, name: str) -> TableSnapshot | None:
        return self.tables.get(name)

    def flat_rows(self) -> dict[str, str]:
        """The legacy flat map ("table:rowid" → value) for old consumers."""
        flat: dict[str, str] = {}
        for name in self.table_names():
            snapshot = self.tables[name]
            for row_id, value in snapshot.rows.items():
                flat[f"{name}{TABLE_PREFIX_SEPARATOR}{row_id}"] = value
        return flat

    def to_dict(self) -> dict[str, Any]:
        """The wire form: the legacy keys PLUS the per-table breakdown.

        The legacy keys are what every existing consumer reads; the
        ``tables`` key is what a new consumer should read. Emitting both
        keeps this an addition rather than a migration.
        """
        return {
            "method": self.method,
            "rows": self.flat_rows(),
            "note": self.note,
            "source": self.source,
            "tables": {
                name: self.tables[name].to_dict() for name in self.table_names()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DbSnapshot:
        """Rebuild a snapshot from either the new or the legacy wire form."""
        if not isinstance(data, Mapping):
            return cls(method=METHOD_NONE, note="snapshot is not a mapping")
        method = str(data.get("method") or METHOD_NONE)
        note = str(data.get("note") or "")
        source = str(data.get("source") or "")
        raw_tables = data.get("tables")
        tables: dict[str, TableSnapshot] = {}
        if isinstance(raw_tables, Mapping):
            for name, body in raw_tables.items():
                rows = body.get("rows") if isinstance(body, Mapping) else None
                if isinstance(rows, Mapping):
                    tables[str(name)] = TableSnapshot(
                        table=str(name),
                        rows={str(k): str(v) for k, v in rows.items()},
                    )
        if tables:
            return cls(method=method, tables=tables, note=note, source=source)
        raw_rows = data.get("rows")
        if isinstance(raw_rows, Mapping):
            tables = parse_dump_rows(raw_rows)
        return cls(method=method, tables=tables, note=note, source=source)

    @classmethod
    def none(cls, note: str) -> DbSnapshot:
        """A snapshot that carries no evidence, and says why."""
        return cls(method=METHOD_NONE, note=note)


def parse_dump_rows(rows: Mapping[str, str]) -> dict[str, TableSnapshot]:
    """Split the flat dump map into per-table snapshots.

    A key without a table prefix (no ":") cannot be attributed to a
    table. It is NOT dropped silently — it lands in a table named
    ``_unattributed`` so a reader can see that something was dumped but
    could not be placed. Losing a row would be losing evidence.
    """
    tables: dict[str, dict[str, str]] = {}
    for key, value in rows.items():
        text = str(key)
        if TABLE_PREFIX_SEPARATOR in text:
            table, _, row_id = text.partition(TABLE_PREFIX_SEPARATOR)
            table = table.strip() or "_unattributed"
            row_id = row_id.strip()
        else:
            table = "_unattributed"
            row_id = text.strip()
        tables.setdefault(table, {})[row_id] = str(value)
    return {
        name: TableSnapshot(table=name, rows=dict(tables[name]))
        for name in sorted(tables)
    }


@dataclass(frozen=True)
class DbDifference:
    """One table's difference between the two snapshots."""

    table: str
    kind: str
    changed_rows: tuple[str, ...] = ()
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "kind": self.kind,
            "changed_rows": list(self.changed_rows),
            "detail": self.detail,
        }


def compare_snapshots(
    base: DbSnapshot, head: DbSnapshot
) -> list[DbDifference]:
    """Compare two snapshots table by table, discovering the tables.

    Table-agnostic on purpose: the tables come from the snapshots, so a
    domain nobody listed is still compared. The differences are returned
    in table order (deterministic); which one matters is the caller's
    policy decision.
    """
    if not base.has_evidence() or not head.has_evidence():
        return []

    names = sorted(set(base.tables) | set(head.tables))
    differences: list[DbDifference] = []
    for name in names:
        base_table = base.tables.get(name) or TableSnapshot(table=name)
        head_table = head.tables.get(name) or TableSnapshot(table=name)
        if base_table.is_empty() and head_table.is_empty():
            continue
        changed = sorted(
            row_id
            for row_id in set(base_table.rows) & set(head_table.rows)
            if base_table.rows[row_id] != head_table.rows[row_id]
        )
        added = sorted(set(head_table.rows) - set(base_table.rows))
        removed = sorted(set(base_table.rows) - set(head_table.rows))
        if not (changed or added or removed):
            continue
        details: list[str] = []
        for row_id in changed[:6]:
            details.append(
                f"row {row_id}: '{base_table.rows[row_id]}' -> "
                f"'{head_table.rows[row_id]}'"
            )
        for row_id in added[:6]:
            details.append(f"row {row_id} appeared (head only)")
        for row_id in removed[:6]:
            details.append(f"row {row_id} disappeared (base only)")
        kind = DIFF_CHANGED if changed else (DIFF_ADDED if added else DIFF_REMOVED)
        differences.append(
            DbDifference(
                table=name,
                kind=kind,
                changed_rows=tuple(changed + added + removed),
                detail="; ".join(details),
            )
        )
    return differences


def differences_to_dicts(differences: list[DbDifference]) -> list[dict[str, Any]]:
    """JSON-ready projection of the differences."""
    return [difference.to_dict() for difference in differences]


class SnapshotCollector(Protocol):
    """A source of database state snapshots.

    The seam that lets an H2-file dump and a Testcontainers dump be
    swapped without any consumer noticing: they both return a
    ``DbSnapshot``.
    """

    def collect(self, workspace: str) -> DbSnapshot: ...


__all__ = [
    "DIFF_ADDED",
    "DIFF_CHANGED",
    "DIFF_REMOVED",
    "METHOD_H2_FILE_DUMP",
    "METHOD_NONE",
    "METHOD_TESTCONTAINERS",
    "ROW_VALUE_SEPARATOR",
    "TABLE_PREFIX_SEPARATOR",
    "DbDifference",
    "DbSnapshot",
    "SnapshotCollector",
    "TableSnapshot",
    "compare_snapshots",
    "differences_to_dicts",
    "parse_dump_rows",
]
