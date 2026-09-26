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
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKIP_DIRS = {
    ".venv", "node_modules", ".git", "dist", ".local", ".specraft",
    ".mypy_cache", ".pytest_cache", "worktrees",
}
# Dirs where an unpinned capture is a defect, not debt.
PINNED_SCOPES = {
    "agent", "api", "cli", "craft", "sandbox", "storage", "providers",
    "integrations", "evidence", "ops",
}
SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}

# Measured with this gate's own lens (subprocess calls only: `text=` or
# `universal_newlines=` without `encoding=`) at 74750fc. Two earlier numbers of
# mine were wrong and are retracted here: 66 came from a loose scan that counted
# model constructors with a `text=` field (`RepoRule(...)`, `BuiltPrompt(...)`),
# and a "6 unpinned file reads" claim counted `open(..., "rb")` binary reads.
# Shrink this number; never let it grow.
DEBT_CEILING = 55


def _is_subprocess_call(node: ast.Call) -> bool:
    func = node.func
    name = getattr(func, "attr", None) or getattr(func, "id", None)
    if name not in SUBPROCESS_FUNCS:
        return False
    if isinstance(func, ast.Attribute):
        return getattr(func.value, "id", "") in ("subprocess",) or name == "communicate"
    return False


def captures_without_codec(root: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if set(path.parts) & SKIP_DIRS:
            continue
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
            offenders.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return offenders


def test_pinned_scopes_never_decode_a_child_with_the_locale_codec() -> None:
    scope_dirs = [REPO / name for name in sorted(PINNED_SCOPES)]
    offenders = [o for d in scope_dirs if d.is_dir() for o in captures_without_codec(d)]
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
