"""craft/editor.py unit tests — atomic writes, backups, uniqueness, audit, EOL."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from craft.editor import MAX_READ_LINES, AuditEntry, EditError, Editor

FIXED_CLOCK = "2026-08-18T00:00:00+00:00"


def make_editor(tmp_path: Path) -> Editor:
    return Editor(
        tmp_path,
        backup_dir=tmp_path / ".specraft" / "backup",
        audit_path=tmp_path / ".specraft" / "audit.jsonl",
        clock=lambda: FIXED_CLOCK,
    )


def test_read_file_returns_line_numbers(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n", encoding="utf-8")
    assert make_editor(tmp_path).read_file("f.txt") == [(1, "a"), (2, "b"), (3, "c")]


def test_read_file_offset_and_limit(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n", encoding="utf-8")
    assert make_editor(tmp_path).read_file("f.txt", offset=2, limit=1) == [(2, "b")]


def test_read_file_limit_capped_at_2000(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x\n" * 5, encoding="utf-8")
    with pytest.raises(EditError, match="2000"):
        make_editor(tmp_path).read_file("f.txt", limit=MAX_READ_LINES + 1)


def test_read_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(EditError, match="不存在"):
        make_editor(tmp_path).read_file("nope.txt")


def test_write_file_preserves_lf_line_endings(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    editor.write_file("calc.py", "a = 1\nb = 2\n")
    raw = (tmp_path / "calc.py").read_bytes()
    assert raw == b"a = 1\nb = 2\n"
    assert b"\r\n" not in raw


def test_write_file_preserves_crlf_line_endings(tmp_path: Path) -> None:
    (tmp_path / "win.py").write_bytes(b"old\r\nfile\r\n")
    editor = make_editor(tmp_path)
    editor.write_file("win.py", "p\nq\n")
    assert (tmp_path / "win.py").read_bytes() == b"p\r\nq\r\n"


def test_write_file_backs_up_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "calc.py"
    target.write_text("old content\n", encoding="utf-8")
    editor = make_editor(tmp_path)
    editor.write_file("calc.py", "new content\n")
    backups = list((tmp_path / ".specraft" / "backup").iterdir())
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old content\n"


def test_write_file_new_file_creates_parents_without_backup(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    editor.write_file("sub/dir/new.py", "x\n")
    assert (tmp_path / "sub" / "dir" / "new.py").read_text(encoding="utf-8") == "x\n"
    assert not (tmp_path / ".specraft" / "backup").exists()


def test_apply_edit_unique_replaces(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_text("a\nb\nc\n", encoding="utf-8")
    editor = make_editor(tmp_path)
    editor.apply_edit("f.txt", "b", "X")
    assert target.read_text(encoding="utf-8") == "a\nX\nc\n"
    assert "edit" in [entry.action for entry in editor.audit]


def test_apply_edit_non_unique_refuses_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_text("a\nb\na\n", encoding="utf-8")
    editor = make_editor(tmp_path)
    with pytest.raises(EditError, match="2 处"):
        editor.apply_edit("f.txt", "a", "x")
    assert target.read_text(encoding="utf-8") == "a\nb\na\n"
    assert not (tmp_path / ".specraft" / "backup").exists()
    edit_entries = [entry for entry in editor.audit if entry.action == "edit"]
    assert edit_entries and "拒绝" in edit_entries[0].detail


def test_apply_edit_no_match_raises(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_text("hello\n", encoding="utf-8")
    editor = make_editor(tmp_path)
    with pytest.raises(EditError, match="未命中"):
        editor.apply_edit("f.txt", "zzz", "y")
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_apply_edit_empty_old_raises(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(EditError, match="old 不能为空"):
        make_editor(tmp_path).apply_edit("f.txt", "", "y")


def test_move_backs_up_and_moves(tmp_path: Path) -> None:
    (tmp_path / "old.py").write_text("payload\n", encoding="utf-8")
    editor = make_editor(tmp_path)
    editor.move("old.py", "new.py")
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "payload\n"
    assert not (tmp_path / "old.py").exists()
    backups = list((tmp_path / ".specraft" / "backup").iterdir())
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "payload\n"


def test_move_target_exists_raises(tmp_path: Path) -> None:
    (tmp_path / "old.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("b\n", encoding="utf-8")
    with pytest.raises(EditError, match="目标已存在"):
        make_editor(tmp_path).move("old.py", "new.py")


def test_delete_backs_up_and_removes(tmp_path: Path) -> None:
    (tmp_path / "gone.py").write_text("bye\n", encoding="utf-8")
    editor = make_editor(tmp_path)
    editor.delete("gone.py")
    assert not (tmp_path / "gone.py").exists()
    backups = list((tmp_path / ".specraft" / "backup").iterdir())
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "bye\n"


def test_audit_entries_carry_timestamp_action_path(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    editor.write_file("a.txt", "1\n")
    editor.apply_edit("a.txt", "1", "2")
    editor.delete("a.txt")
    assert editor.audit
    for entry in editor.audit:
        assert isinstance(entry, AuditEntry)
        assert entry.timestamp == FIXED_CLOCK
        assert entry.action
        assert entry.path
    assert {entry.action for entry in editor.audit} >= {"write", "edit", "delete"}


def test_audit_lines_are_persisted_as_jsonl(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    editor.write_file("a.txt", "1\n")
    lines = (tmp_path / ".specraft" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        entry = json.loads(line)
        assert set(entry) >= {"timestamp", "action", "path"}


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    with pytest.raises(EditError, match="越界"):
        editor.write_file("../evil.txt", "x")
    with pytest.raises(EditError, match="越界"):
        editor.read_file(str(tmp_path.parent / "outside.txt"))


def test_delete_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(EditError, match="不存在"):
        make_editor(tmp_path).delete("nope.txt")
