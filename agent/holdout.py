"""Holdout registry — declared eval-case isolation (interview hardening).

A holdout set keeps a fixed list of evaluation case ids out of the pool
that training / tuning / quick iteration sees, so eval metrics on those
cases stay meaningful. The single source of truth is the human-owned
manifest at ``docs/eval/holdout-manifest.json``; this module only
loads, validates and partitions against it. It never mutates the manifest
and never touches the network.

Honesty contract: the current manifest was declared AFTER earlier eval
rounds already ran against these cases (W-series eval reports and the
10-case Recall/Precision runs recorded in CLAUDE.md), so the isolation is
retroactive and partial. Consumers must surface that caveat whenever they
report holdout metrics — the manifest ``note`` field carries the same
wording.

Integration note (cli/specproof/commands/eval.py): at commit time that
file was modified by another lane (git status: ``M
cli/specproof/commands/eval.py``), so the ``--exclude-holdout`` flag
was deliberately NOT added here to avoid a write conflict. The intended
wiring, for when that lane clears: after ``eval_cmd`` computes
``case_dirs``, load ``HoldoutRegistry`` (default manifest) and drop
every directory whose name satisfies ``registry.is_holdout(name)``
unless an ``--include-holdout`` flag is passed, then print the
skipped-case count in the run summary. The manifest
``integration_note`` field carries the same text.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACTIVE_HOLDOUT_STATUSES: frozenset[str] = frozenset({"candidate", "active"})
KNOWN_STATUSES: frozenset[str] = frozenset({"candidate", "active", "released"})

DEFAULT_MANIFEST_PATH: Path = (
    Path(__file__).resolve().parent.parent / "docs" / "eval" / "holdout-manifest.json"
)


class HoldoutError(ValueError):
    """Holdout manifest missing, unreadable, malformed or invalid."""


@dataclass(frozen=True)
class HoldoutEntry:
    """One declared holdout case (the manifest row shape)."""

    case_id: str
    family: str
    added_at: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "case_id": self.case_id,
            "family": self.family,
            "added_at": self.added_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class HoldoutPartition:
    """A case list split into holdout and training ids (input order kept)."""

    holdout: list[str]
    training: list[str]

    @property
    def holdout_count(self) -> int:
        return len(self.holdout)

    @property
    def training_count(self) -> int:
        return len(self.training)

    def to_dict(self) -> dict[str, Any]:
        return {"holdout": list(self.holdout), "training": list(self.training)}


class HoldoutRegistry:
    """Loaded, validated holdout manifest plus partition/report helpers."""

    def __init__(
        self,
        entries: list[HoldoutEntry],
        *,
        note: str = "",
        integration_note: str = "",
        manifest_path: str = "",
    ) -> None:
        self._entries: list[HoldoutEntry] = sorted(
            entries, key=lambda entry: entry.case_id
        )
        self._by_id: dict[str, HoldoutEntry] = {
            entry.case_id: entry for entry in self._entries
        }
        self.note: str = note
        self.integration_note: str = integration_note
        self.manifest_path: str = manifest_path

    @classmethod
    def load(cls, manifest_path: str | Path | None = None) -> HoldoutRegistry:
        path = Path(manifest_path) if manifest_path is not None else DEFAULT_MANIFEST_PATH
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HoldoutError(f"holdout manifest 无法读取: {path} ({exc})") from exc
        try:
            raw: Any = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise HoldoutError(f"holdout manifest 不是合法 JSON: {path} ({exc})") from exc
        if not isinstance(raw, dict):
            raise HoldoutError(f"holdout manifest 顶层必须是对象: {path}")
        raw_note = raw.get("note")
        raw_integration_note = raw.get("integration_note")
        note = raw_note if isinstance(raw_note, str) else ""
        integration_note = (
            raw_integration_note if isinstance(raw_integration_note, str) else ""
        )
        case_rows = raw.get("cases")
        if not isinstance(case_rows, list):
            raise HoldoutError(f"holdout manifest 缺少 cases 列表: {path}")
        entries: list[HoldoutEntry] = []
        seen: set[str] = set()
        for index, row in enumerate(case_rows):
            if not isinstance(row, dict):
                raise HoldoutError(f"holdout manifest case[{index}] 不是对象: {path}")
            missing = [
                field
                for field in ("case_id", "family", "added_at", "status")
                if not isinstance(row.get(field), str)
            ]
            if missing:
                raise HoldoutError(
                    f"holdout manifest case[{index}] 缺少字符串字段: {', '.join(missing)}"
                )
            case_id = str(row["case_id"])
            family = str(row["family"])
            added_at = str(row["added_at"])
            status = str(row["status"])
            if not case_id.strip():
                raise HoldoutError(f"holdout manifest case[{index}] case_id 为空")
            if case_id in seen:
                raise HoldoutError(f"holdout manifest 重复 case_id: {case_id}")
            if status not in KNOWN_STATUSES:
                raise HoldoutError(
                    f"holdout manifest case[{index}] status 非法: {status!r} "
                    f"(允许: {', '.join(sorted(KNOWN_STATUSES))})"
                )
            seen.add(case_id)
            entries.append(
                HoldoutEntry(
                    case_id=case_id, family=family, added_at=added_at, status=status
                )
            )
        return cls(
            entries,
            note=note,
            integration_note=integration_note,
            manifest_path=str(path),
        )

    def cases(self) -> list[HoldoutEntry]:
        """All declared entries, sorted by case_id."""
        return list(self._entries)

    def is_holdout(self, case_id: str) -> bool:
        """True when case_id is declared with a holdout-active status.

        ``candidate`` and ``active`` are holdout; ``released``
        ids return to the training pool and undeclared ids are not holdout.
        """
        entry = self._by_id.get(case_id)
        return entry is not None and entry.status in ACTIVE_HOLDOUT_STATUSES

    def partition(self, case_ids: Sequence[str]) -> HoldoutPartition:
        """Split case_ids into (holdout, training), preserving input order.

        Duplicate inputs are preserved as-is on the side they land on.
        """
        holdout: list[str] = []
        training: list[str] = []
        for case_id in case_ids:
            if self.is_holdout(case_id):
                holdout.append(case_id)
            else:
                training.append(case_id)
        return HoldoutPartition(holdout=holdout, training=training)

    def by_family(self) -> dict[str, list[str]]:
        """family -> declared case ids (sorted within each family)."""
        families: dict[str, list[str]] = {}
        for entry in self._entries:
            families.setdefault(entry.family, []).append(entry.case_id)
        return families

    def summary(self) -> dict[str, Any]:
        """Machine-readable counts: total, holdout_total, by_status, by_family."""
        by_status: dict[str, int] = {}
        families: dict[str, list[str]] = {}
        for entry in self._entries:
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
            families.setdefault(entry.family, []).append(entry.case_id)
        return {
            "manifest_path": self.manifest_path,
            "total": len(self._entries),
            "holdout_total": sum(
                1 for entry in self._entries if entry.status in ACTIVE_HOLDOUT_STATUSES
            ),
            "by_status": by_status,
            "by_family": {family: len(ids) for family, ids in families.items()},
            "note": self.note,
        }

    def report(self) -> str:
        """Deterministic human-readable report (stable ordering throughout)."""
        by_status: dict[str, int] = {}
        families: dict[str, list[str]] = {}
        for entry in self._entries:
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
            families.setdefault(entry.family, []).append(entry.case_id)
        status_text = ", ".join(
            f"{status}={count}" for status, count in sorted(by_status.items())
        )
        lines = [
            "HoldoutRegistry report",
            f"manifest: {self.manifest_path}",
            f"total: {len(self._entries)} cases ({status_text})",
            "by family:",
        ]
        for family in sorted(families):
            lines.append(f"  {family}: {', '.join(families[family])}")
        if self.note:
            lines.append("note: " + self.note)
        if self.integration_note:
            lines.append("integration: " + self.integration_note)
        return "\n".join(lines)


__all__ = [
    "ACTIVE_HOLDOUT_STATUSES",
    "DEFAULT_MANIFEST_PATH",
    "KNOWN_STATUSES",
    "HoldoutEntry",
    "HoldoutError",
    "HoldoutPartition",
    "HoldoutRegistry",
]
