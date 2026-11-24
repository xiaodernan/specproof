"""Gate: the push seatbelt is wired, and it would actually stop a push.

WHAT WAS MEASURED (before this gate existed).  The encoding gate (#1545) went
live on 2026-11-09.  On 2026-11-19 a lane committed a UTF-16LE file.  The gate
caught it — in CI, on GitHub, four days later than anyone noticed.  The
repository had **no local pre-push hook at all** (`.git/hooks` held two
10-byte no-op stubs), so on the machine where the damage was done there was no
signal between "committed" and "somebody reads GitHub".

So the seatbelt exists: `.githooks/pre-push` runs a short list of the
repository's own gates against the tree that is about to be pushed, in a
detached worktree, so a dirty working tree cannot raise a false alarm.

A seatbelt nobody checks is decoration.  This gate is the check.

THE RULES:

  R1  the wiring is still there: the hook exists, it calls the runner, and it
      does not swallow the runner's exit code.  (`|| true` here is the one
      edit that turns the seatbelt into a comment.)
  R2  the runner runs REAL gates: the list is not collapsed, every gate file
      is one the repository actually carries, and the encoding gate — the one
      that would have caught the UTF-16LE file — is among them.
  R3  the seatbelt refuses.  Proved live: a synthetic failing gate must make
      the runner exit non-zero, and a synthetic passing gate must make it
      exit zero.  A runner that always says "fine" is the disease.
  R4  installing the seatbelt does not take over the owner's machine: the
      installer writes the REPOSITORY-local config only, and the global
      pre-commit hook is delegated to, never replaced.  Proved live, in a
      throwaway repository.

WHAT THIS GATE DOES NOT SAY.  It does not run the seatbelt against this
repository's own tree — that is what the hook does at push time, and it takes
a worktree and a few gates.  It also does not say the seatbelt is installed
on this machine: `core.hooksPath` is local configuration, not repository
state, and a gate that demanded a machine-specific setting would be red on
every other clone.  The installer is the documented way to turn it on.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "prepush_gates.py"
INSTALLER = ROOT / "scripts" / "install_repo_hooks.py"
HOOK_DIR = ROOT / ".githooks"
PRE_PUSH = HOOK_DIR / "pre-push"
PRE_COMMIT = HOOK_DIR / "pre-commit"

#: The gate that would have caught the UTF-16LE file.  If the seatbelt stops
#: running it, the seatbelt stops being the answer to that failure.
ENCODING_GATE = "tests/unit/test_tracked_files_survive_their_encoding.py"


def _load(path: Path) -> Any:
    """Load a script by file path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


runner = _load(RUNNER)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _code_lines(text: str) -> list[str]:
    """The hook's code, with the prose taken out.

    A comment cannot swallow an exit code, so a comment that *mentions* one is
    not a defect.  The first version of this gate read the whole file and
    flagged the sentence that warned against `|| true` — a ruler wider than the
    thing it measures.
    """
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


def test_the_seatbelt_is_wired_to_the_runner_and_does_not_swallow_its_verdict() -> None:
    """R1 — the hook is there and it means what it says."""
    assert PRE_PUSH.is_file(), f"{PRE_PUSH} is missing — the seatbelt is unwired"
    text = PRE_PUSH.read_text(encoding="utf-8")
    assert "prepush_gates.py" in text, (
        "the pre-push hook does not call the runner — it does nothing"
    )
    code = _code_lines(text)
    assert any(line.startswith("exec ") for line in code), (
        "the pre-push hook must `exec` the runner so the runner's exit code "
        "IS the hook's exit code"
    )
    for neutraliser in ("|| true", "|| :", "; true"):
        assert not any(neutraliser in line for line in code), (
            f"the pre-push hook contains `{neutraliser}` in its code — that "
            "swallows the runner's verdict and turns the seatbelt into decoration"
        )
    assert PRE_COMMIT.is_file(), (
        f"{PRE_COMMIT} is missing — the owner's global pre-commit hook would "
        "be replaced instead of delegated to"
    )
    delegate = PRE_COMMIT.read_text(encoding="utf-8")
    delegate_code = _code_lines(delegate)
    assert any("--global" in line for line in delegate_code), (
        "the repository's pre-commit hook must look the owner's global hook up "
        "at run time"
    )
    assert any(line.startswith("exec ") for line in delegate_code), (
        "the repository's pre-commit hook must delegate to the owner's global "
        "hook rather than replace it"
    )


def test_the_seatbelt_runs_real_gates_and_includes_the_encoding_gate() -> None:
    """R2 — the gate list is not collapsed, and it is not decorative."""
    gates = runner.GATES
    assert len(gates) >= 3, (
        f"the seatbelt runs {len(gates)} gate(s) — a list this short is not a "
        "census, it is a preference"
    )
    missing = [rel for _label, rel in gates if not (ROOT / rel).is_file()]
    assert not missing, (
        f"the seatbelt runs gate files the repository does not carry: {missing}"
    )
    labels = {label for label, _rel in gates}
    assert len(labels) == len(gates), "two seatbelt gates share a label"
    assert ENCODING_GATE in [rel for _rel_label, rel in gates], (
        "the seatbelt does not run the encoding gate — the one that catches a "
        "UTF-16LE file, which is the failure this seatbelt was built for"
    )


def test_the_seatbelt_refuses_a_red_gate_and_passes_a_green_one() -> None:
    """R3 — proved live, because a runner that always says fine is the disease."""
    tmp = Path(tempfile.mkdtemp(prefix="seatbelt-selftest-"))
    try:
        (tmp / "test_synthetic_red.py").write_text(
            "def test_red():\n    assert False, 'synthetic red'\n", encoding="utf-8")
        (tmp / "test_synthetic_green.py").write_text(
            "def test_green():\n    assert True\n", encoding="utf-8")

        red = runner.run_gates(["test_synthetic_red.py"], tmp)
        assert red != 0, (
            "the seatbelt ran a failing gate and reported success — it would "
            "not have stopped the UTF-16LE push"
        )
        green = runner.run_gates(["test_synthetic_green.py"], tmp)
        assert green == 0, (
            f"the seatbelt ran a passing gate and reported {green} — it would "
            "block every push, which is the other way to be broken"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_installing_the_seatbelt_touches_only_this_repository() -> None:
    """R4 — the owner's global configuration is not this repository's business."""
    global_before = _git(ROOT, "config", "--global", "--get", "core.hooksPath").stdout.strip()

    tmp = Path(tempfile.mkdtemp(prefix="seatbelt-install-"))
    try:
        _git(tmp, "init", "--quiet")
        (tmp / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(INSTALLER, tmp / "scripts" / "install_repo_hooks.py")
        shutil.copytree(HOOK_DIR, tmp / ".githooks")

        python = Path(sys.executable)
        first = subprocess.run([str(python), str(tmp / "scripts" / "install_repo_hooks.py")],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace")
        assert first.returncode == 0, f"the installer failed: {first.stderr[:300]}"
        installed = _git(tmp, "config", "--local", "--get", "core.hooksPath").stdout.strip()
        assert installed == ".githooks", (
            f"the installer left core.hooksPath = {installed!r} — the seatbelt "
            "would not be wired"
        )

        second = subprocess.run([str(python), str(tmp / "scripts" / "install_repo_hooks.py")],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace")
        assert second.returncode == 0, "the installer is not idempotent"
        again = _git(tmp, "config", "--local", "--get", "core.hooksPath").stdout.strip()
        assert again == ".githooks", "running the installer twice changed the setting"

        global_after = _git(ROOT, "config", "--global", "--get", "core.hooksPath").stdout.strip()
        assert global_after == global_before, (
            "installing the seatbelt changed the GLOBAL core.hooksPath — the "
            "owner's machine configuration was rewritten"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
