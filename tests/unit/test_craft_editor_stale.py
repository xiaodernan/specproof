"""craft/editor.py stale-digest + workspace-change classification tests (计划书 §8.1/§8.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from craft.editor import (
    EditError,
    Editor,
    FileRead,
    StaleContextError,
    classify_workspace_changes,
    sha256_digest,
)

FIXED_CLOCK = "2026-08-18T00:00:00+00:00"


def make_editor(tmp_path: Path) -> Editor:
    return Editor(
        tmp_path,
        backup_dir=tmp_path / ".specraft" / "backup",
        audit_path=tmp_path / ".specraft" / "audit.jsonl",
        clock=lambda: FIXED_CLOCK,
    )


# -- digests -------------------------------------------------------------------


def test_sha256_digest_is_over_raw_bytes() -> None:
    assert sha256_digest(b"abc") == sha256_digest(b"abc")
    assert len(sha256_digest(b"abc")) == 64
    assert sha256_digest(b"abc") != sha256_digest(b"abd")


def test_file_digest_and_read_file_meta(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_bytes(b"a\nb\n")
    editor = make_editor(tmp_path)
    expected = sha256_digest(b"a\nb\n")
    assert editor.file_digest("f.txt") == expected
    meta = editor.read_file_meta("f.txt")
    assert isinstance(meta, FileRead)
    assert meta.digest == expected
    assert meta.size == 4
    assert meta.lines == [(1, "a"), (2, "b")]


def test_file_digest_missing_file_is_empty(tmp_path: Path) -> None:
    assert make_editor(tmp_path).file_digest("nope.txt") == ""


def test_read_file_keeps_legacy_list_return(tmp_path: Path) -> None:
    """Backward compatibility: read_file still returns a plain line list."""
    (tmp_path / "f.txt").write_text("a\nb\n", encoding="utf-8")
    result = make_editor(tmp_path).read_file("f.txt")
    assert result == [(1, "a"), (2, "b")]
    assert not hasattr(result, "digest")


# -- write_file with expected_digest -------------------------------------------


def test_write_file_matching_digest_writes_and_audits_digests(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_bytes(b"old\n")
    editor = make_editor(tmp_path)
    editor.write_file("f.txt", "new\n", expected_digest=sha256_digest(b"old\n"))
    assert target.read_bytes() == b"new\n"
    write_entries = [entry for entry in editor.audit if entry.action == "write"]
    assert len(write_entries) == 1
    assert write_entries[0].before_digest == sha256_digest(b"old\n")
    assert write_entries[0].after_digest == sha256_digest(b"new\n")


def test_write_file_stale_digest_refuses_and_leaves_file_untouched(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_bytes(b"user edited\n")
    editor = make_editor(tmp_path)
    with pytest.raises(StaleContextError, match="STALE_CONTEXT") as exc_info:
        editor.write_file("f.txt", "agent overwrite\n", expected_digest=sha256_digest(b"old\n"))
    assert isinstance(exc_info.value, EditError)
    assert target.read_bytes() == b"user edited\n"
    assert not (tmp_path / ".specraft" / "backup").exists()
    refused = [entry for entry in editor.audit if "STALE_CONTEXT" in entry.detail]
    assert refused and refused[0].before_digest == sha256_digest(b"user edited\n")


def test_write_file_new_file_with_empty_expected_digest(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    editor.write_file("new.txt", "x\n", expected_digest="")
    assert (tmp_path / "new.txt").read_bytes() == b"x\n"


def test_write_file_new_file_with_nonempty_expected_digest_is_stale(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    with pytest.raises(StaleContextError, match="STALE_CONTEXT"):
        editor.write_file("new.txt", "x\n", expected_digest=sha256_digest(b"whatever\n"))
    assert not (tmp_path / "new.txt").exists()


def test_write_file_without_digest_behaves_legacy(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_bytes(b"old\n")
    editor = make_editor(tmp_path)
    editor.write_file("f.txt", "new\n")  # positional call, no digest
    assert target.read_bytes() == b"new\n"


# -- apply_edit with expected_digest -------------------------------------------


def test_apply_edit_matching_digest_applies(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_bytes(b"a\nb\n")
    editor = make_editor(tmp_path)
    editor.apply_edit("f.txt", "b", "X", expected_digest=sha256_digest(b"a\nb\n"))
    assert target.read_bytes() == b"a\nX\n"


def test_apply_edit_stale_digest_refuses_before_uniqueness(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_bytes(b"changed\n")
    editor = make_editor(tmp_path)
    with pytest.raises(StaleContextError, match="STALE_CONTEXT"):
        editor.apply_edit(
            "f.txt", "changed", "x", expected_digest=sha256_digest(b"stale\n")
        )
    assert target.read_bytes() == b"changed\n"


def test_apply_edit_without_digest_behaves_legacy(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"
    target.write_bytes(b"a\nb\n")
    editor = make_editor(tmp_path)
    editor.apply_edit("f.txt", "b", "X")  # legacy positional call
    assert target.read_bytes() == b"a\nX\n"


def test_audit_jsonl_carries_digest_fields(tmp_path: Path) -> None:
    editor = make_editor(tmp_path)
    editor.write_file("a.txt", "1\n", expected_digest="")
    lines = (tmp_path / ".specraft" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        entry = json.loads(line)
        assert set(entry) >= {
            "timestamp",
            "action",
            "path",
            "detail",
            "before_digest",
            "after_digest",
        }


# -- classify_workspace_changes -------------------------------------------------


def test_classify_user_modification() -> None:
    result = classify_workspace_changes(" M calc.py\n")
    assert result["user_changes"] == ["calc.py"]
    assert result["agent_changes"] == []
    assert result["unknown"] == []


def test_classify_agent_modification_via_agent_paths() -> None:
    result = classify_workspace_changes(" M calc.py\n", agent_paths=["calc.py"])
    assert result["agent_changes"] == ["calc.py"]
    assert result["user_changes"] == []


def test_classify_untracked_is_unknown_unless_agent() -> None:
    result = classify_workspace_changes("?? scratch.py\n")
    assert result["unknown"] == ["scratch.py"]
    agent = classify_workspace_changes("?? new.py\n", agent_paths=["new.py"])
    assert agent["agent_changes"] == ["new.py"]
    assert agent["unknown"] == []


def test_classify_conflict_is_unknown() -> None:
    result = classify_workspace_changes("UU conflicted.py\n")
    assert result["unknown"] == ["conflicted.py"]
    assert result["user_changes"] == []
    assert result["agent_changes"] == []


def test_classify_rename_unknown_unless_destination_is_agent() -> None:
    result = classify_workspace_changes("R  old.py -> new.py\n")
    assert result["unknown"] == ["new.py"]
    agent = classify_workspace_changes("R  old.py -> new.py\n", agent_paths=["new.py"])
    assert agent["agent_changes"] == ["new.py"]


def test_classify_deleted_and_ignored() -> None:
    result = classify_workspace_changes(" D gone.py\n!! ignored.log\n")
    assert result["user_changes"] == ["gone.py"]
    assert result["unknown"] == []


def test_classify_empty_output() -> None:
    result = classify_workspace_changes("")
    assert result == {"user_changes": [], "agent_changes": [], "unknown": []}


def test_classify_duplicate_paths_are_deduped() -> None:
    result = classify_workspace_changes(" M a.py\n M a.py\n", agent_paths=["a.py"])
    assert result["agent_changes"] == ["a.py"]


def test_classify_crlf_lines_are_accepted() -> None:
    result = classify_workspace_changes(" M a.py\r\n")
    assert result["user_changes"] == ["a.py"]
