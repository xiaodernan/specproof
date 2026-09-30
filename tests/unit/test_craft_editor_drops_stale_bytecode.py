"""#134 — a same-length fix must not be hidden from the loop's own check.

Measured premise (CI run 36613910190): six CraftLoop convergence tests assert
DONE and get STUCK, the child pytest keeps printing ``assert 2.0 == 8``, and
the log carries NO anchor rejection ("apply_edit 被拒" / "old 未命中" -> 0
hits). The fix landed on disk; the verification could not see it.

The mechanism is CPython's bytecode cache: a .pyc is validated against the
source's mtime in WHOLE SECONDS plus its size. These loops' fix strings are
same-length ("return x / 2" -> "return x * 2") and a child run costs ~0.03s on
CI, so the edit lands inside the second the previous child already compiled.
Reproduced on this host with the timing pinned
(.scratch/g134/probe.py): run1 rc=1 -> same-size/same-second atomic replace ->
run2 rc=1 "1 failed", while ``__pycache__/calc.cpython-312.pyc`` is still the
pre-fix bytecode.

Cases:
1. With the mtime pinned to the pre-edit second, the loop must still reach
   DONE (``Editor._atomic_write`` drops the stale cache).
2. Control arm: neuter the cache drop and the SAME pinned loop must be STUCK —
   this is what makes case 1 a measurement instead of a coincidence.
3. The drop touches no audit entry (the published diff stays honest) and
   leaves a non-python file's sibling cache alone.
"""

from __future__ import annotations

import os
from pathlib import Path

from craft.editor import Editor
from craft.loop import CraftLoop
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text

SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"
BUGGY = "def double(x):\n    return x / 2\n"
FIXED = "def double(x):\n    return x * 2\n"
TEST_SRC = "from calc import double\n\n\ndef test_double():\n    assert double(4) == 8\n"

assert len(BUGGY) == len(FIXED), "the whole defect is the identical byte count"


def write_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(BUGGY, encoding="utf-8", newline="\n")
    (tmp_path / "test_calc.py").write_text(TEST_SRC, encoding="utf-8", newline="\n")


def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def pin_mtime(editor: Editor) -> None:
    """Make every write land inside the second the file was last compiled.

    Models the CI timing deterministically: the child's .pyc header keeps the
    mtime the fixture was created at, so a later edit that restores that mtime
    (same seconds, same size) validates against the stale bytecode.
    """
    real = editor._atomic_write

    def wrapped(target: Path, content: str, style: str) -> None:
        before = target.stat().st_mtime_ns if target.exists() else None
        real(target, content, style)
        if before is not None:
            os.utime(target, ns=(before, before))

    editor._atomic_write = wrapped  # type: ignore[method-assign]


def run_loop(tmp_path: Path) -> dict[str, object]:
    write_repo(tmp_path)
    spec = parse_spec_text(SPEC)
    loop = CraftLoop(
        spec,
        compile_plan(spec),
        tmp_path,
        job_id="job-pin",
        fix_registry={"test": fix_double},
        exec_mode="local",
    )
    pin_mtime(loop.editor)
    return loop.run()


def test_a_same_second_same_length_fix_is_still_seen_by_the_check(tmp_path: Path) -> None:
    report = run_loop(tmp_path)
    assert report["result"] == "DONE", report
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == FIXED


def test_the_pinned_loop_is_stuck_when_the_cache_is_not_dropped(
    tmp_path: Path, monkeypatch
) -> None:
    """Control arm: the defect is the bytecode cache, nothing else."""
    monkeypatch.setattr(
        Editor, "_drop_stale_bytecode", staticmethod(lambda target: None)
    )
    report = run_loop(tmp_path)
    assert report["result"] == "STUCK", report
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == FIXED


def test_the_drop_removes_only_the_edited_modules_cached_bytecode(tmp_path: Path) -> None:
    write_repo(tmp_path)
    editor = Editor(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "calc.cpython-312.pyc").write_bytes(b"stale")
    (cache / "calc.cpython-312-pytest-9.pyc").write_bytes(b"stale")
    (cache / "other.cpython-312.pyc").write_bytes(b"kept")
    (tmp_path / "notes.py.txt").write_text("a\n", encoding="utf-8")
    (cache / "notes.py.txt.cpython-312.pyc").write_bytes(b"kept")

    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    assert not (cache / "calc.cpython-312.pyc").exists()
    assert not (cache / "calc.cpython-312-pytest-9.pyc").exists()
    assert (cache / "other.cpython-312.pyc").read_bytes() == b"kept"

    editor.apply_edit("notes.py.txt", "a", "b")
    assert (cache / "notes.py.txt.cpython-312.pyc").read_bytes() == b"kept"
    # The drop must stay out of the published diff: report.diff_stat is
    # derived from the audit's write/edit/move/delete entries.
    touched = {
        entry.path for entry in editor.audit if entry.action in ("write", "edit", "move", "delete")
    }
    assert touched == {"calc.py", "notes.py.txt"}
    assert not [
        entry
        for entry in editor.audit
        if "pycache" in entry.path or "pycache" in entry.detail
    ]
