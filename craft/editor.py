"""M1 code-editing toolset (design doc §4.3).

- read_file: line-numbered reads, capped at 2000 lines per call;
- write_file: whole-file atomic write (temp file + os.replace), existing
  content backed up to .specraft/backup/ first, line-ending convention
  preserved (LF stays LF, CRLF stays CRLF);
- apply_edit: precise substring replace — old must match exactly once,
  otherwise an error is raised and nothing touches the disk (drift guard);
- move/delete: backup first, then act;
- every operation appends an audit line (timestamp/action/path), optionally
  persisted to an audit.jsonl.

All paths are relative to the workspace root; absolute paths and ".."
escapes are rejected.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MAX_READ_LINES = 2000


class EditError(RuntimeError):
    """An edit could not be applied (and nothing was written)."""


@dataclass(frozen=True)
class AuditEntry:
    timestamp: str
    action: str
    path: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "path": self.path,
            "detail": self.detail,
        }


def _default_clock() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Editor:
    """Workspace-scoped editor with backups and an in-memory audit list."""

    def __init__(
        self,
        workspace: str | Path,
        backup_dir: str | Path | None = None,
        audit_path: str | Path | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.backup_dir = (
            Path(backup_dir) if backup_dir is not None else self.workspace / ".specraft" / "backup"
        )
        self.audit_path = Path(audit_path) if audit_path is not None else None
        self._clock = clock or _default_clock
        self.audit: list[AuditEntry] = []

    # -- internals -------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        raw = Path(path)
        if raw.is_absolute():
            raise EditError(f"路径越界: 不允许绝对路径 ({path})")
        target = (self.workspace / raw).resolve()
        if not target.is_relative_to(self.workspace):
            raise EditError(f"路径越界: {path} 超出 workspace 根")
        return target

    def _audit(self, action: str, path: str, detail: str = "") -> None:
        entry = AuditEntry(timestamp=self._clock(), action=action, path=path, detail=detail)
        self.audit.append(entry)
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            raise EditError(f"审计写入失败 ({self.audit_path}): {exc}") from exc

    def _backup(self, target: Path) -> None:
        if not target.is_file():
            return
        relative = target.relative_to(self.workspace).as_posix().replace("/", "__")
        stamp = self._clock().replace(":", "").replace("+", "Z").replace("-", "")
        name = f"{relative}.{stamp}.{secrets.token_hex(3)}"
        destination = self.backup_dir / name
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
        except OSError as exc:
            raise EditError(f"备份失败 ({target}): {exc}") from exc
        self._audit("backup", str(target.relative_to(self.workspace)), f"→ {name}")

    @staticmethod
    def _detect_newline(target: Path) -> str:
        with target.open("rb") as handle:
            head = handle.read(64 * 1024)
        return "CRLF" if b"\r\n" in head else "LF"

    def _atomic_write(self, target: Path, content: str, style: str) -> None:
        tmp = target.parent / f".{target.name}.{secrets.token_hex(6)}.tmp"
        normalized = content.replace("\r\n", "\n")
        if style == "CRLF":
            normalized = normalized.replace("\n", "\r\n")
        try:
            with tmp.open("w", encoding="utf-8", newline="") as handle:
                handle.write(normalized)
            os.replace(tmp, target)
        except OSError as exc:
            with suppress(OSError):
                tmp.unlink()
            raise EditError(f"原子写失败 ({target}): {exc}") from exc

    # -- public toolset --------------------------------------------------

    def read_file(
        self, path: str, offset: int = 1, limit: int = MAX_READ_LINES
    ) -> list[tuple[int, str]]:
        """Line-numbered read; at most MAX_READ_LINES lines per call."""
        if offset < 1:
            raise EditError(f"offset 必须 ≥ 1 (收到 {offset})")
        if limit > MAX_READ_LINES:
            raise EditError(f"limit={limit} 超过单次读取上限 {MAX_READ_LINES}")
        target = self._resolve(path)
        if not target.is_file():
            raise EditError(f"文件不存在: {path}")
        text = target.read_text(encoding="utf-8")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        window = lines[offset - 1 : offset - 1 + limit]
        result = [(offset + index, line) for index, line in enumerate(window)]
        self._audit("read", path, f"lines {offset}-{offset + len(window) - 1} ({len(window)} 行)")
        return result

    def write_file(self, path: str, content: str) -> None:
        """Whole-file atomic write; existing files are backed up first."""
        target = self._resolve(path)
        if target.is_file():
            style = self._detect_newline(target)
            self._backup(target)
        else:
            style = "LF"
            target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, content, style)
        self._audit("write", path, f"{len(content)} chars")

    def apply_edit(self, path: str, old: str, new: str) -> None:
        """Precise edit: old must match exactly once or nothing is written."""
        if old == "":
            raise EditError("apply_edit 的 old 不能为空字符串")
        target = self._resolve(path)
        if not target.is_file():
            raise EditError(f"文件不存在: {path}")
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            self._audit("edit", path, "拒绝: old 未命中任何位置")
            raise EditError(f"apply_edit 拒绝: old 未命中 ({path})")
        if count > 1:
            self._audit("edit", path, f"拒绝: old 命中 {count} 处, 不唯一")
            raise EditError(f"apply_edit 拒绝: old 命中 {count} 处不唯一, 未落盘 ({path})")
        style = self._detect_newline(target)
        self._backup(target)
        self._atomic_write(target, text.replace(old, new, 1), style)
        self._audit("edit", path, f"替换 1 处 ({len(old)}→{len(new)} chars)")

    def move(self, src: str, dst: str) -> None:
        source = self._resolve(src)
        destination = self._resolve(dst)
        if not source.is_file():
            raise EditError(f"源文件不存在: {src}")
        if destination.exists():
            raise EditError(f"目标已存在: {dst}")
        self._backup(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(source, destination)
        except OSError as exc:
            raise EditError(f"移动失败 ({src} → {dst}): {exc}") from exc
        self._audit("move", src, f"→ {dst}")

    def delete(self, path: str) -> None:
        target = self._resolve(path)
        if not target.is_file():
            raise EditError(f"文件不存在: {path}")
        self._backup(target)
        try:
            target.unlink()
        except OSError as exc:
            raise EditError(f"删除失败 ({path}): {exc}") from exc
        self._audit("delete", path, "")
