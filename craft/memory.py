"""Task-level fact memory (GRAND_PLAN_V2 卷 XXI §21.1) — craft/memory.py.

TaskMemory is the task-scoped fact base for one SpecCraft job. It stores
compact, deterministic facts (never reasoning text — ADR-017) and is the
only thing that survives across craft resume:

- kinds: file_read | file_written | error_signature | decision | budget;
- dedupe policy is fixed and deterministic:
    file_read / file_written  -> merge by (kind, detail), timestamp moves
                                to the latest observation;
    error_signature           -> merge by (kind, detail), count accumulates
                                (the stuck-detection counter becomes a
                                persisted fact);
    budget                    -> keep only the latest snapshot;
    decision                  -> append (every terminal verdict is a fact).
- save()/load() round-trip through <artifact_dir>/memory.json (atomic
  write); a missing file loads as an empty memory (old jobs stay
  resumable), a corrupt file raises MemoryError — loud, never silent.
- summarize_for_prompt() is the ONLY injection path: deterministic
  priority file_written > error_signature > decision > file_read >
  budget, one compact line per entry, whole-entry truncation at
  limit_tokens (≈2000). Callers must put the result into
  prompt_templates.assemble()'s variable_data — never into the stable
  prefix.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MEMORY_KINDS: frozenset[str] = frozenset(
    {"file_read", "file_written", "error_signature", "decision", "budget"}
)

# Lower rank = emitted first (卷 XXI §21.1 priority order).
_KIND_PRIORITY: dict[str, int] = {
    "file_written": 0,
    "error_signature": 1,
    "decision": 2,
    "file_read": 3,
    "budget": 4,
}

DEFAULT_SUMMARY_TOKEN_LIMIT = 2000
MEMORY_SCHEMA_VERSION = 1
MEMORY_FILENAME = "memory.json"
_CHARS_PER_TOKEN_ESTIMATE = 4


class MemoryError(ValueError):
    """memory.json is unreadable or structurally invalid."""


@dataclass(frozen=True)
class MemoryEntry:
    kind: str
    detail: str
    step_id: str
    ts: str
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "step_id": self.step_id,
            "ts": self.ts,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        kind = data.get("kind")
        detail = data.get("detail")
        step_id = data.get("step_id", "")
        ts = data.get("ts", "")
        count = data.get("count", 1)
        if not isinstance(kind, str) or kind not in MEMORY_KINDS:
            raise MemoryError(f"memory 条目 kind 非法: {kind!r}")
        if not isinstance(detail, str) or not detail.strip():
            raise MemoryError(f"memory 条目 ({kind}) detail 缺失或为空")
        if not isinstance(step_id, str) or not isinstance(ts, str):
            raise MemoryError(f"memory 条目 ({kind}) step_id/ts 应为字符串")
        if not isinstance(count, int) or count < 1:
            raise MemoryError(f"memory 条目 ({kind}) count 应为正整数")
        return cls(kind=kind, detail=detail, step_id=step_id, ts=ts, count=count)


def _default_ts() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TaskMemory:
    """Task-scoped deterministic fact base (in-memory + memory.json)."""

    def __init__(
        self,
        entries: list[MemoryEntry] | None = None,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self._entries: list[MemoryEntry] = list(entries or [])
        self._now = now_fn or _default_ts

    @property
    def entries(self) -> list[MemoryEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    # -- write -----------------------------------------------------------

    def add(
        self,
        kind: str,
        detail: str,
        *,
        step_id: str = "",
        count: int = 1,
    ) -> MemoryEntry:
        """Add one fact with the fixed dedupe policy (see module docstring).

        Returns the stored entry (merged or appended).
        """
        if kind not in MEMORY_KINDS:
            raise MemoryError(f"memory kind 非法: {kind!r} (仅支持 {sorted(MEMORY_KINDS)})")
        if not isinstance(detail, str) or not detail.strip():
            raise MemoryError(f"memory detail 不能为空 (kind={kind!r})")
        if not isinstance(step_id, str):
            raise MemoryError("memory step_id 应为字符串")
        if not isinstance(count, int) or count < 1:
            raise MemoryError("memory count 应为正整数")
        ts = self._now()
        if kind != "decision":
            # budget merges by kind alone (latest snapshot wins); every
            # other mergeable kind merges by (kind, detail).
            for index, entry in enumerate(self._entries):
                if entry.kind != kind:
                    continue
                if kind != "budget" and entry.detail != detail:
                    continue
                merged = MemoryEntry(
                    kind=kind,
                    detail=detail,
                    step_id=step_id or entry.step_id,
                    ts=ts,
                    count=entry.count + count if kind == "error_signature" else 1,
                )
                self._entries[index] = merged
                return merged
        entry = MemoryEntry(kind=kind, detail=detail, step_id=step_id, ts=ts, count=count)
        self._entries.append(entry)
        return entry

    def remove(self, kind: str, detail: str) -> bool:
        """Delete the first entry matching (kind, detail); True when one was
        removed."""
        for index, entry in enumerate(self._entries):
            if entry.kind == kind and entry.detail == detail:
                self._entries.pop(index)
                return True
        return False

    def clear(self) -> None:
        self._entries.clear()

    # -- prompt injection --------------------------------------------------

    def summarize_for_prompt(
        self, limit_tokens: int = DEFAULT_SUMMARY_TOKEN_LIMIT
    ) -> str:
        """Deterministic, budget-capped summary for prompt variable_data.

        Entries are emitted in kind-priority order (file_written first),
        oldest first within a kind; one compact line per entry; whole
        entries are dropped once the token estimate would exceed the
        limit — never partial lines, never a different order.
        """
        if limit_tokens <= 0:
            raise MemoryError("summarize_for_prompt 的 limit_tokens 必须为正")
        ordered = sorted(
            self._entries,
            key=lambda entry: (
                _KIND_PRIORITY.get(entry.kind, 99),
                entry.ts,
                entry.detail,
                entry.step_id,
            ),
        )
        lines: list[str] = []
        used = 0
        for entry in ordered:
            count_part = f" x{entry.count}" if entry.count > 1 else ""
            line = f"[{entry.kind}] {entry.detail} (step {entry.step_id}){count_part}"
            cost = max(1, len(line) // _CHARS_PER_TOKEN_ESTIMATE + 1)
            if lines and used + cost > limit_tokens:
                break
            lines.append(line)
            used += cost
        return "\n".join(lines)

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": MEMORY_SCHEMA_VERSION,
            "entries": [entry.to_dict() for entry in self._entries],
        }

    def save(self, artifact_dir: str | Path) -> Path:
        """Atomically write memory.json into artifact_dir (created if needed)."""
        directory = Path(artifact_dir)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MemoryError(f"无法创建产物目录 ({directory}): {exc}") from exc
        target = directory / MEMORY_FILENAME
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"
        tmp = directory / f".{MEMORY_FILENAME}.{secrets.token_hex(6)}.tmp"
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
            os.replace(tmp, target)
        except OSError as exc:
            with suppress(OSError):
                tmp.unlink()
            raise MemoryError(f"memory.json 写入失败 ({target}): {exc}") from exc
        return target

    @classmethod
    def load(cls, artifact_dir: str | Path) -> TaskMemory:
        """Restore from <artifact_dir>/memory.json.

        A missing file loads as an empty memory (older jobs stay
        resumable). A corrupt file raises MemoryError — loud, never
        silently dropped.
        """
        target = Path(artifact_dir) / MEMORY_FILENAME
        if not target.is_file():
            return cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MemoryError(f"memory.json 无法读取 ({target}): {exc}") from exc
        if not isinstance(data, dict):
            raise MemoryError("memory.json 顶层必须是对象")
        raw_entries = data.get("entries", [])
        if not isinstance(raw_entries, list):
            raise MemoryError("memory.json 的 entries 应为数组")
        entries: list[MemoryEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise MemoryError("memory.json 的条目应为对象")
            entries.append(MemoryEntry.from_dict(raw))
        return cls(entries=entries)
