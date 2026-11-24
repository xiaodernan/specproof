#!/usr/bin/env python
"""install_repo_hooks.py — point this repository's hooks at `.githooks/`.

WHY.  The repository's gates live in the repository, so the hook that runs
them should live in the repository too — otherwise the seatbelt exists only
as a line in a commit message.  Git reads hooks from `core.hooksPath`, which
on this machine points at a *global* directory (`C:/Users/18414/.codex/git-hooks`)
holding the owner's pre-commit tool.

This script sets `core.hooksPath = .githooks` for **this repository only** and
nothing else.  The global configuration is never written: `.githooks/pre-commit`
delegates to the global hook instead of replacing it, so the owner's tool keeps
running exactly as before.

Idempotent: running it twice changes nothing the second time.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ".githooks"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def current() -> str | None:
    proc = _git("config", "--local", "--get", "core.hooksPath")
    value = proc.stdout.strip()
    return value or None


def install() -> int:
    if not (ROOT / HOOKS_DIR).is_dir():
        print(f"[install_repo_hooks] {HOOKS_DIR}/ is missing — nothing to install")
        return 2
    before = current()
    _git("config", "--local", "core.hooksPath", HOOKS_DIR)
    after = current()
    if after != HOOKS_DIR:
        print("[install_repo_hooks] FAILED to set core.hooksPath")
        return 2
    if before == HOOKS_DIR:
        print(f"[install_repo_hooks] already installed (core.hooksPath = {after})")
        return 0
    print(f"[install_repo_hooks] installed: core.hooksPath {before or '(unset)'} "
          f"-> {after}")
    print("  the global pre-commit hook is delegated to, not replaced")
    return 0


def uninstall() -> int:
    before = current()
    if before is None:
        print("[install_repo_hooks] nothing to uninstall (no local core.hooksPath)")
        return 0
    _git("config", "--local", "--unset", "core.hooksPath")
    print(f"[install_repo_hooks] uninstalled: core.hooksPath {before} -> (unset)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true",
                        help="remove the repository-local core.hooksPath")
    args = parser.parse_args()
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())
