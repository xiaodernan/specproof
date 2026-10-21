"""Verify a golden case on its TAGS: the base passes, the head fails.

A golden case is a CLAIM: "this repository is correct, and that head
introduces a defect the experiments must catch" (base_pass_head_fail).
The claim is only worth something if it is checked against the committed
tags — not against a local edit, and not against a chat log.

This script does exactly that:

  1. it renders the generated experiment source (the same contract set
     the golden snapshot pins),
  2. it checks out `base` and the case's head tag into throwaway
     worktrees, drops the generated test into the demo's test tree,
  3. it runs maven on both sides,
  4. it reports whether the claim holds: base green, head red.

Requirements: maven on PATH, and a JDK the demo's tests can run on
(JDK <= 21 — the demo's Mockito inline mock maker cannot instrument
RabbitTemplate on JDK 25, so the suite fails to start there; set
JAVA_HOME to a JDK 17/21 install).

    python scripts/verify_case_tags.py --case case-101
    python scripts/verify_case_tags.py --case case-29 --keep
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED_TEST = REPO_ROOT / "tests" / "unit" / "test_generated_test_source_is_pinned.py"
TEST_REL = (
    "demo/spring-backend/src/test/java/com/specproof/demo/"
    "SpecProofGeneratedTest.java"
)
MAVEN = os.environ.get("SPECPROOF_MVN", "mvn")


def _generated_source() -> str:
    """The source the pipeline writes — the same one the golden pins."""
    sys.path.insert(0, str(REPO_ROOT))
    from agent.nodes.generate_counterexamples import (  # noqa: PLC0415
        _build_deterministic_test,
    )

    spec = importlib.util.spec_from_file_location("pinned", PINNED_TEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contracts = [dict(c) for c in module.CONTRACTS]
    return _build_deterministic_test(contracts)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _run_maven(workdir: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [
            "cmd", "/c", MAVEN,
            "-o", "-Djava.version=17",
            "-Dtest=SpecProofGeneratedTest", "-DfailIfNoTests=false", "test",
        ],
        cwd=str(workdir / "demo" / "spring-backend"),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _summary(out: str) -> list[str]:
    keys = (
        "Tests run:", "FAILURE!", "must survive", "accepted an order",
        "BUILD ", "Could not initialize plugin", "currently in creation",
    )
    lines = [line.strip()[:200] for line in out.splitlines()
             if any(k in line for k in keys)]
    return lines[-12:]


def _check_side(ref: str, source: str, keep: bool) -> tuple[int, str]:
    workdir = Path(tempfile.mkdtemp(prefix="sp-case-verify-"))
    _git("worktree", "add", "-q", "--detach", str(workdir), ref)
    test_file = workdir / TEST_REL
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(source, encoding="utf-8")
    try:
        code, out = _run_maven(workdir)
    finally:
        if not keep:
            _git("worktree", "remove", "--force", str(workdir))
    return code, out


def _jdk_note() -> str:
    """A human sentence about the JDK, or "" when the JDK is fine.

    The demo's tests need a JDK the inline mock maker can instrument.
    On a newer JDK the failure reads "Mockito cannot mock this class:
    RabbitTemplate" — a sentence about the mock maker, not about what
    to do. The tool that runs the demo's tests should say the thing the
    reader can act on.
    """
    import re
    import subprocess

    try:
        out = subprocess.run(
            ["java", "-version"], capture_output=True, text=True, timeout=15,
        ).stderr
    except Exception:  # noqa: BLE001 — no java, the build will say so
        return ""
    found = re.search(r'version "(\d+)', out)
    if not found:
        return ""
    major = int(found.group(1))
    if major <= 21:
        return ""
    return (
        f"NOTE: this JDK is {major}. The demo's tests need JDK 21 or lower — "
        f"the inline mock maker cannot instrument RabbitTemplate on a newer "
        f"JDK, and the failure reads 'Mockito cannot mock this class' "
        f"rather than anything actionable. Set JAVA_HOME to a JDK 17/21 "
        f"install and retry."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True,
                        help="the case id, e.g. case-101")
    parser.add_argument("--base", default="base")
    parser.add_argument("--head", default="",
                        help="the head tag (default: <case>-head)")
    parser.add_argument("--keep", action="store_true",
                        help="keep the throwaway worktrees")
    args = parser.parse_args()

    head = args.head or (args.case + "-head")
    source = _generated_source()

    note = _jdk_note()
    if note:
        print(note)

    print(f"=== {args.base} ===")
    base_code, base_out = _check_side(args.base, source, args.keep)
    for line in _summary(base_out):
        print(" ", line)
    print(f"exit: {base_code}")

    print(f"=== {head} ===")
    head_code, head_out = _check_side(head, source, args.keep)
    for line in _summary(head_out):
        print(" ", line)
    print(f"exit: {head_code}")

    holds = base_code == 0 and head_code != 0
    print()
    print(f"VERDICT: {args.case} base_pass_head_fail "
          f"{'HOLDS' if holds else 'DOES NOT HOLD'}")
    return 0 if holds else 1


if __name__ == "__main__":
    raise SystemExit(main())
