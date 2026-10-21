"""Fault injection: the disk is full (errno 28) — Phase 3, P3-7.

The other disk fault (tests/fault/test_fault_matrix.py) fails
``os.replace``. ENOSPC does not arrive there: it arrives at the WRITE (a
partial temp file), at the BACKUP copy, or at the AUDIT append. Those are
three different failure points with three different truths about what the
disk now contains, and only the last one can leave the caller misinformed
about a write that already happened.

Measured before the fix: a full disk on the final audit append raised
``EditError("审计写入失败")`` — "the edit failed" — while the file HAD
been replaced. The model then retried with the same ``expected_digest``
and was told STALE_CONTEXT: stuck, holding a file it believed it never
wrote. That is the shape this file pins.
"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from craft.editor import AuditError, EditError, Editor, sha256_digest

ENOSPC = OSError(errno.ENOSPC, "No space left on device")


class _FailingHandle:
    """A file handle whose writes fail, optionally after N successful ones."""

    def __init__(self, inner: object, owner: dict[str, int]) -> None:
        self._inner = inner
        self._owner = owner

    def __enter__(self) -> _FailingHandle:
        self._inner.__enter__()  # type: ignore[attr-defined]
        return self

    def __exit__(self, *exc: object) -> object:
        return self._inner.__exit__(*exc)  # type: ignore[attr-defined]

    def write(self, data: str) -> int:
        self._owner["writes"] += 1
        if self._owner["writes"] >= self._owner["fail_from"]:
            raise ENOSPC
        return self._inner.write(data)  # type: ignore[attr-defined,no-any-return]

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def _fail_writes_to(
    monkeypatch: pytest.MonkeyPatch, suffix: str, *, fail_from: int = 1
) -> dict[str, int]:
    """Make every write to a path ending in `suffix` fail with ENOSPC."""
    state = {"writes": 0, "fail_from": fail_from}
    real_open = Path.open

    def failing_open(self: Path, *args: object, **kwargs: object) -> object:
        handle = real_open(self, *args, **kwargs)  # type: ignore[arg-type]
        if str(self).endswith(suffix):
            return _FailingHandle(handle, state)
        return handle

    monkeypatch.setattr(Path, "open", failing_open)
    return state


def _tmp_files(workspace: Path) -> list[str]:
    return sorted(p.name for p in workspace.rglob("*.tmp"))


# ══════════════════════════════════════════════════════════════════
# The three no-write fault points: nothing changes, and nothing lies
# ══════════════════════════════════════════════════════════════════


class TestAFullDiskBeforeTheWriteChangesNothing:
    def test_enospc_on_the_temp_write_keeps_the_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        _fail_writes_to(monkeypatch, ".tmp")

        with pytest.raises(EditError) as caught:
            Editor(str(tmp_path)).write_file("src.txt", "replacement\n")

        # Not an AuditError: nothing landed, so "the edit failed" is true.
        assert not isinstance(caught.value, AuditError)
        assert "原子写失败" in str(caught.value)
        assert target.read_text(encoding="utf-8") == "original\n"
        assert _tmp_files(tmp_path) == [], (
            "a partial temp file was left on disk — the next writer inherits "
            "debris it did not create"
        )

    def test_enospc_on_the_backup_keeps_the_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        monkeypatch.setattr(
            "craft.editor.shutil.copy2",
            lambda *a, **k: (_ for _ in ()).throw(ENOSPC),
        )

        with pytest.raises(EditError) as caught:
            Editor(str(tmp_path)).write_file("src.txt", "replacement\n")

        assert not isinstance(caught.value, AuditError)
        assert "备份失败" in str(caught.value)
        assert target.read_text(encoding="utf-8") == "original\n"

    def test_enospc_on_the_first_audit_is_a_plain_edit_error(
        self, tmp_path: Path
    ) -> None:
        """The backup's audit runs BEFORE the write — nothing has landed.

        It must stay a plain EditError: the promise "nothing was written"
        is still true here, and a landed-write error would be a lie in the
        other direction.
        """
        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        monkeypatch_state = {"writes": 0, "fail_from": 1}
        real_open = Path.open

        def failing_open(self: Path, *args: object, **kwargs: object) -> object:
            handle = real_open(self, *args, **kwargs)  # type: ignore[arg-type]
            if str(self).endswith("audit.log"):
                return _FailingHandle(handle, monkeypatch_state)
            return handle

        Path.open = failing_open  # type: ignore[method-assign]
        try:
            with pytest.raises(EditError) as caught:
                Editor(str(tmp_path), audit_path=str(tmp_path / "audit.log")).write_file(
                    "src.txt", "replacement\n"
                )
        finally:
            Path.open = real_open  # type: ignore[method-assign]

        assert not isinstance(caught.value, AuditError)
        assert target.read_text(encoding="utf-8") == "original\n"


# ══════════════════════════════════════════════════════════════════
# The one that lands: the caller must be told the truth
# ══════════════════════════════════════════════════════════════════


class TestAFullDiskAfterTheWriteSaysSo:
    """The file changed. An "edit failed" message would be a lie."""

    def _write_with_broken_audit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        # First append (the backup) succeeds; the second (the write) fails.
        _fail_writes_to(monkeypatch, "audit.log", fail_from=2)
        with pytest.raises(AuditError):
            Editor(str(tmp_path), audit_path=str(tmp_path / "audit.log")).write_file(
                "src.txt", "replacement\n"
            )
        return target

    def test_the_file_is_actually_replaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = self._write_with_broken_audit(tmp_path, monkeypatch)
        assert target.read_text(encoding="utf-8") == "replacement\n"

    def test_the_error_says_the_write_landed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        _fail_writes_to(monkeypatch, "audit.log", fail_from=2)
        with pytest.raises(AuditError) as caught:
            Editor(str(tmp_path), audit_path=str(tmp_path / "audit.log")).write_file(
                "src.txt", "replacement\n"
            )
        message = str(caught.value)
        assert "已落地" in message
        assert "文件已经改变" in message
        assert caught.value.landed is True

    def test_it_is_not_an_edit_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """EditError promises "nothing was written" — this is the opposite.

        If a caller caught this as an EditError it would retry the same
        write and be refused as STALE_CONTEXT, which is the stuck state
        the measurement found.
        """
        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        _fail_writes_to(monkeypatch, "audit.log", fail_from=2)
        with pytest.raises(AuditError) as caught:
            Editor(str(tmp_path), audit_path=str(tmp_path / "audit.log")).write_file(
                "src.txt", "replacement\n"
            )
        assert not isinstance(caught.value, EditError)

    def test_the_retry_with_the_old_digest_would_be_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pin WHY the message matters: the naive retry cannot work.

        This is not a defect — it is the reason the error must say the
        write landed. A model that reads "edit failed" retries, and the
        digest gate then refuses it: the two errors together leave it
        stuck with a file it believes is unchanged.
        """
        from craft.editor import StaleContextError

        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        _fail_writes_to(monkeypatch, "audit.log", fail_from=2)
        editor = Editor(str(tmp_path), audit_path=str(tmp_path / "audit.log"))
        with pytest.raises(AuditError):
            editor.write_file("src.txt", "replacement\n")

        monkeypatch.undo()
        with pytest.raises(StaleContextError):
            editor.write_file(
                "src.txt",
                "replacement again\n",
                expected_digest=sha256_digest(b"original\n"),
            )
        # The second attempt changed nothing.
        assert target.read_text(encoding="utf-8") == "replacement\n"

    def test_the_in_memory_audit_still_records_the_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The on-disk log is missing the entry; the session's list is not.

        The write happened, so the in-memory record is the truth — it is
        the FILE log that is short one line.
        """
        target = tmp_path / "src.txt"
        target.write_text("original\n", encoding="utf-8")
        _fail_writes_to(monkeypatch, "audit.log", fail_from=2)
        editor = Editor(str(tmp_path), audit_path=str(tmp_path / "audit.log"))
        with pytest.raises(AuditError):
            editor.write_file("src.txt", "replacement\n")

        assert [entry.action for entry in editor.audit] == ["backup", "write"]
        monkeypatch.undo()
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, "only the backup made it into the log"
        assert target.read_text(encoding="utf-8") == "replacement\n"


# ══════════════════════════════════════════════════════════════════
# What the MODEL sees: a distinct tool code, not EDIT_REJECTED
# ══════════════════════════════════════════════════════════════════


class TestTheModelIsToldWhichOfTheTwoHappened:
    def test_the_tool_code_separates_landed_from_rejected(self) -> None:
        from craft.tools import (
            CODE_EDIT_LANDED_AUDIT_FAILED,
            CODE_EDIT_REJECTED,
            ERROR_CODES,
        )

        assert CODE_EDIT_LANDED_AUDIT_FAILED != CODE_EDIT_REJECTED
        # Both are error-status codes, so both are counted by _error().
        assert CODE_EDIT_LANDED_AUDIT_FAILED in ERROR_CODES
        assert CODE_EDIT_REJECTED in ERROR_CODES

    def test_a_landed_write_is_dispatched_with_its_own_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from craft.tools import (
            CODE_EDIT_LANDED_AUDIT_FAILED,
            ToolRegistry,
        )

        (tmp_path / "src.txt").write_text("original\n", encoding="utf-8")
        _fail_writes_to(monkeypatch, "audit.log", fail_from=2)
        registry = ToolRegistry(
            tmp_path,
            editor=Editor(str(tmp_path), audit_path=str(tmp_path / "audit.log")),
        )

        result = registry.dispatch(
            registry.build_tool_call(
                "create_file", {"path": "src.txt", "content": "replacement\n"}
            )
        )

        assert result.summary.startswith(f"[{CODE_EDIT_LANDED_AUDIT_FAILED}]")
        assert (tmp_path / "src.txt").read_text(encoding="utf-8") == "replacement\n"
