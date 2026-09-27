"""#92 — every child-process capture must name its codec.

Measured, not theorised: `subprocess.run(..., text=True)` decodes with
`locale.getpreferredencoding()`, which on this Chinese Windows host is cp936.
Set `PYTHONIOENCODING=utf-8` — the encoding the repo's own RUNBOOK tells
operators to use for CJK output — and the child emits UTF-8 while the parent
still decodes as cp936. The reader thread then dies inside `subprocess`, the
failure is printed as a stray traceback, and **`CompletedProcess.stdout` comes
back as `None`**. No caller checks for that. So in the product a failed decode
looks like "the command printed nothing": a Maven/pytest/git capture that
silently reads as empty is a false-green vector in a verification platform.

That is how four unit tests on master were failing (`test_bench_aider`,
`test_swebench_harness` x2, `test_swebench_llm`): `assert flag in proc.stdout`
raised `TypeError: argument of type 'NoneType' is not iterable`, and it failed
in a clean worktree and in the main tree alike — not environment noise.

The gate below pins subprocess captures to an explicit codec and ratchets the
rest of the repo. File reads opened with `text=True` are a sibling problem and
are listed in `docs/operations/DRILLS.md` rather than quietly folded in here.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKIP_DIRS = {
    "node_modules", ".git", "dist", ".local", ".specraft",
    ".mypy_cache", ".pytest_cache", "worktrees",
}
# A virtualenv is recognised by what makes one, not by what the operator named
# it: `pyvenv.cfg`, or the conventional names, or `site-packages`. Hard-coding
# `.venv` here measured 55 at 74750fc; the moment a second env named `.venv312`
# existed on the machine the lens reported 67 with not one line of product code
# changed — twelve third-party captures in someone else's site-packages. A gate
# whose number moves when the disk gains an environment measures the machine,
# not the repo, so the next `.venv-anything` must be skipped too.
VENVISH = {"venv", ".venv", "site-packages", "dist-packages"}
# Dirs where an unpinned capture is a defect, not debt.
PINNED_SCOPES = {
    "agent", "api", "cli", "craft", "sandbox", "storage", "providers",
    "integrations", "evidence", "ops", "mcp", "contracts", "observability",
}
SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}

# Measured with this gate's own lens (subprocess calls only: `text=` or
# `universal_newlines=` without `encoding=`) at 74750fc. Two earlier numbers of
# mine were wrong and are retracted here: 66 came from a loose scan that counted
# model constructors with a `text=` field (`RepoRule(...)`, `BuiltPrompt(...)`),
# and a "6 unpinned file reads" claim counted `open(..., "rb")` binary reads.
# Re-measured at bbdfa0c after venvs were excluded by marker rather than by the
# single name `.venv`: 55 — exactly this ceiling, zero headroom. It counts only
# the repo's own files now, so it moves when the repo moves.
# #111 pinned the one shipped MCP capture (`mcp/tools.py` read a child's UTF-8
# with the OS locale and reported mojibake paths as evidence) and brought `mcp`,
# `contracts` and `observability` into PINNED_SCOPES — they are loaded by a
# shipped entry point, so an unpinned read there is a defect, not debt. Those
# three lanes measured 0 offenders, so only the fixed one leaves debt: 55 -> 54.
# The remaining 54 are `scripts/` and `tests/`.
# Shrink this number; never let it grow.
DEBT_CEILING = 54


def _is_subprocess_call(node: ast.Call) -> bool:
    func = node.func
    name = getattr(func, "attr", None) or getattr(func, "id", None)
    if name not in SUBPROCESS_FUNCS:
        return False
    if isinstance(func, ast.Attribute):
        return getattr(func.value, "id", "") in ("subprocess",) or name == "communicate"
    return False


def _is_skipped_dir(directory: Path) -> bool:
    name = directory.name
    return (
        name in SKIP_DIRS
        or name in VENVISH
        or name.startswith(".venv")
        or (directory / "pyvenv.cfg").is_file()
    )


def _repo_python_files(root: Path) -> list[Path]:
    """Walk with pruning: a skipped directory must not even be opened.

    The previous `rglob` walked every venv on disk and AST-parsed its
    site-packages, so this gate alone took minutes and then reported those
    files as repo debt.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_skipped_dir(Path(dirpath) / d)]
        found += [Path(dirpath) / f for f in filenames if f.endswith(".py")]
    return sorted(found)


def captures_without_codec(root: Path, base: Path | None = None) -> list[str]:
    base = root if base is None else base
    offenders: list[str] = []
    for path in _repo_python_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # a file this gate cannot read is a finding
            offenders.append(f"{path}: unparseable: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_subprocess_call(node):
                continue
            names = [k.arg for k in node.keywords]
            if not ({"text", "universal_newlines"} & set(names)):
                continue
            if "encoding" in names:
                continue
            offenders.append(f"{path.relative_to(base).as_posix()}:{node.lineno}")
    return offenders


def test_pinned_scopes_never_decode_a_child_with_the_locale_codec() -> None:
    scope_dirs = [REPO / name for name in sorted(PINNED_SCOPES)]
    offenders = [
        o for d in scope_dirs if d.is_dir() for o in captures_without_codec(d, base=REPO)
    ]
    assert not offenders, (
        "subprocess capture with text=True and no encoding= decodes against the "
        "OS locale; offenders:\n  " + "\n  ".join(offenders)
    )


def test_the_rest_of_the_repo_cannot_grow_the_debt() -> None:
    remaining = captures_without_codec(REPO)
    assert len(remaining) <= DEBT_CEILING, (
        f"{len(remaining)} unpinned child captures (ceiling {DEBT_CEILING}); "
        "new code must name its codec:\n  " + "\n  ".join(remaining[:12])
    )


def test_a_virtualenv_is_skipped_whatever_it_is_called(tmp_path: Path) -> None:
    """Reverse control: the same defect in three directories, one of them counts.

    `.venv312` carries no `pyvenv.cfg` on purpose — it must be caught by the
    name rule; `pyvenv-marker` carries no conventional name — it must be caught
    by the marker rule; only `src` belongs to the repo. Under the old
    `.venv`-only filter all three were scanned, which is how twelve
    third-party captures became the repo's debt.
    """
    src = 'import subprocess\nsubprocess.run(["x"], text=True)\n'
    by_name = tmp_path / ".venv312"
    by_marker = tmp_path / "pyvenv-marker"
    own = tmp_path / "src"
    for directory in (by_name, by_marker, own):
        directory.mkdir()
        (directory / "capture.py").write_text(src, encoding="utf-8")
    (by_marker / "pyvenv.cfg").write_text("home = C:\\Python312\n", encoding="utf-8")

    assert captures_without_codec(tmp_path, base=tmp_path) == ["src/capture.py:2"]


def test_the_failure_mode_is_a_real_decode_failure_not_a_flaky_assertion(
    tmp_path: Path,
) -> None:
    """Deterministic proof of the mechanism, independent of the host's locale.

    The child emits UTF-8 bytes; decoding them as cp936 (what
    `text=True`/no-encoding does on this host) raises, which is why
    `CompletedProcess.stdout` arrives as None instead of the text.
    """
    child = tmp_path / "child.py"
    text = "密钥 \u201d leak\n"
    child_src = "import sys\nsys.stdout.buffer.write(" + repr(text.encode("utf-8")) + ")\n"
    child.write_text(child_src, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(child)], capture_output=True, check=False, timeout=120
    )
    assert proc.stdout == text.encode("utf-8"), proc.stderr[:200]
    with pytest.raises(UnicodeDecodeError):
        proc.stdout.decode("cp936")
    pinned = subprocess.run(
        [sys.executable, str(child)], capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace", timeout=120,
    )
    assert pinned.stdout == text
