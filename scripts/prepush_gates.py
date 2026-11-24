#!/usr/bin/env python
"""prepush_gates.py — the seatbelt at the push end.

WHAT WAS MEASURED (before this script existed).  The encoding gate
(`tests/unit/test_tracked_files_survive_their_encoding.py`, #1545) went live on
2026-11-09.  On 2026-11-19 a lane committed
`docs/evidence/live-lane-probe-2026-11-19-gpt-6.2-sol.txt` in **UTF-16LE**
(776 bytes, `FF FE` BOM) — the shape a Windows shell redirection leaves behind.
The gate caught it.  The file sat on master for four days.

The reason is not that the gate was missing; it is that **the gate's red light
is on the far side of a push**.  `git push` prints the hook's output on the
terminal that is pushing — but the CI job that runs the same gates reports to
GitHub, and nobody was reading GitHub.  This repository has no local
pre-push hook at all (measured: `.git/hooks` held two 10-byte no-op stubs), so
between "committed" and "somebody noticed in CI" there was **no signal at
all** on the machine where the damage was done.

WHAT THIS DOES.  It runs a short list of the repository's own gates against
**the tree that is about to be pushed** — a detached worktree at the pushed
commit, so a dirty working tree (another lane's half-written file) cannot
raise a false alarm, and the gates see the exact bytes that will land on the
remote.  It adds no new rules: it runs the gates that already exist.

WHY THOSE GATES.  The list is the byte plane plus the truth of the evidence:

  * the encoding gate — the one that would have stopped the UTF-16LE file;
  * the ledger's own "evidence claims are true" gate;
  * the evidence-document citation gate (#2082) — a document that points at a
    file the repository does not carry.

WHAT THIS DOES NOT SAY.  It is not the full suite; the full suite is CI's job
(and it is slow).  It says: the tree you are about to publish must not contain
byte-plane damage, and must not make a false claim about a file.  It also does
not run the gates against the *installed package* — the venv is an editable
install pointing at the main checkout, so a gate that imports the package
would read the main tree, not the worktree.  The gates listed here read files,
not the package, so that limit does not bite today; a future gate that
imports the package needs a different seatbelt.

FAIL-CLOSED.  If the seatbelt cannot run — no venv, no worktree, pytest
missing — it refuses the push and says why.  A seatbelt that silently passes
when it is broken is the disease this script exists to cure.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def interpreter() -> Path:
    """The Python that runs the gates.

    The repository's own virtualenv is preferred (it carries pytest and the
    dev dependencies).  `SPECPROOF_PYTHON` overrides it, and when there is no
    virtualenv the interpreter that is running THIS script is used — a clone
    without a .venv still deserves a seatbelt.
    """
    override = os.environ.get("SPECPROOF_PYTHON")
    if override:
        return Path(override)
    if VENV_PYTHON.is_file():
        return VENV_PYTHON
    return Path(sys.executable)

#: (label, gate file) — the gates the seatbelt runs on the pushed tree.
GATES: tuple[tuple[str, str], ...] = (
    ("byte plane", "tests/unit/test_tracked_files_survive_their_encoding.py"),
    ("ledger claims", "tests/unit/test_ledger_evidence_claims_are_true.py"),
    ("evidence citations",
     "tests/unit/test_evidence_documents_cite_paths_the_repository_carries.py"),
)

#: The zero object id — a ref that is being deleted carries it.
ZERO_SHA = "0" * 40


def _run(cmd: list[str], cwd: Path | None = None,
         timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def run_gates(gate_paths: list[str], cwd: Path,
              python: Path | None = None) -> int:
    """Run the given gate files with pytest inside `cwd`.

    Returns pytest's exit code.  The caller decides what a code means; this
    function only runs the gates and reports the code.
    """
    interpreter_path = python or interpreter()
    cmd = [str(interpreter_path), "-m", "pytest", *gate_paths,
           "-q", "-p", "no:randomly", "--no-header"]
    proc = _run(cmd, cwd=cwd)
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return proc.returncode


def pushed_shas(stdin_text: str) -> list[str]:
    """The local object ids this push carries.

    git feeds the hook one line per ref:
        <local ref> SP <local sha> SP <remote ref> SP <remote sha>
    A deletion carries the zero id on the local side, which is nothing to
    check.
    """
    shas: list[str] = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sha = parts[1]
        if sha == ZERO_SHA or sha in shas:
            continue
        shas.append(sha)
    return shas


def _worktree_add(sha: str, path: Path) -> tuple[bool, str]:
    _run(["git", "worktree", "prune"], cwd=ROOT)
    proc = _run(["git", "worktree", "add", "--detach", "--quiet", str(path), sha],
                cwd=ROOT, timeout=600)
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


def _worktree_remove(path: Path) -> None:
    _run(["git", "worktree", "remove", "--force", str(path)], cwd=ROOT, timeout=600)


def check_tree(sha: str) -> tuple[str, str]:
    """Check one pushed commit.  Returns (verdict, detail).

    verdict is GREEN, RED or BROKEN.  BROKEN means the seatbelt could not
    run — which is a refusal, not a pass.
    """
    tmp = Path(tempfile.mkdtemp(prefix="specproof-prepush-"))
    tree = tmp / "tree"
    added, why = _worktree_add(sha, tree)
    if not added:
        _run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT)
        with contextlib.suppress(OSError):
            tmp.rmdir()
        return "BROKEN", f"could not open a worktree at {sha[:12]}: {why}"

    try:
        missing = [rel for _label, rel in GATES if not (tree / rel).is_file()]
        if missing:
            return "BROKEN", (f"the pushed tree does not carry {missing} — the "
                              "seatbelt's own gate list is out of date")
        rc = run_gates([rel for _label, rel in GATES], tree)
        if rc == 0:
            return "GREEN", "every gate passed"
        if rc == 1:
            return "RED", "a gate failed"
        return "BROKEN", f"pytest exited {rc} (that is neither green nor red)"
    finally:
        _worktree_remove(tree)
        with contextlib.suppress(OSError):
            tmp.rmdir()


def main() -> int:
    if os.environ.get("SPECPROOF_SKIP_PREPUSH") == "1":
        print("=" * 72)
        print("[prepush seatbelt] BYPASSED by SPECPROOF_SKIP_PREPUSH=1")
        print("=" * 72)
        return 0

    python = interpreter()
    if not python.is_file():
        print("[prepush seatbelt] BROKEN: no usable interpreter at", python)
        print("  The seatbelt refuses a push it could not check — a seatbelt "
              "that silently passes when it is broken is not a seatbelt.")
        return 2

    shas = pushed_shas(sys.stdin.read())
    if not shas:
        print("[prepush seatbelt] nothing to push")
        return 0

    print(f"[prepush seatbelt] checking {len(shas)} pushed commit(s) "
          f"against {len(GATES)} gate(s) ...")

    worst = 0
    for sha in shas:
        verdict, detail = check_tree(sha)
        print(f"  {sha[:12]}  {verdict}  {detail}")
        if verdict == "RED":
            worst = max(worst, 1)
        elif verdict == "BROKEN":
            worst = max(worst, 2)

    if worst == 0:
        print("[prepush seatbelt] GREEN — the tree you are pushing is clean.")
        return 0
    if worst == 1:
        print("[prepush seatbelt] RED — a gate says the tree you are pushing "
              "is not clean. Fix it, or push with --no-verify and say so in "
              "the commit message.")
        return 1
    print("[prepush seatbelt] BROKEN — the seatbelt could not check the tree. "
          "Refusing the push.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
