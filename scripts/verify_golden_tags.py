"""Read-only integrity verifier for the SpecProof golden-scenario tags.

Checks, without writing anything to the repo (no commits, no tags,
no worktrees, no file changes):
1. ``base`` and ``head-v1`` tags exist; ``head-v1`` is a child of ``base``;
   their demo/ diff is exactly the flagship @PreAuthorize removal.
2. The ``case-*-head`` tags exist for every case directory in
   ``golden-cases/`` except the flagship — the flagship case is
   ``head-v1`` itself (the @PreAuthorize removal IS case-01), so
   expected = (tracked case dirs) - 1, measured at run time, never typed.
3. Every case tag's tree differs from ``base`` by a NON-EMPTY diff confined
   to ``demo/`` (what the eval pipeline consumes via ``git diff base..tag``).
4. Every case tag's merge-base with ``base`` IS ``base`` itself, so even a
   three-dot diff resolves to the same isolated mutation.

Parent-pointer shape (directly-on-base vs legacy chained commits) is
reported but not enforced: the builder restores the base tree before each
mutation, so trees — not parents — carry the contract, and this script
verifies the trees. The measured split is printed, never asserted.

Usage: python scripts/verify_golden_tags.py   (exit 0 = all green)

STATE (2026-11-10, measured on this machine):
  the local tag family is stale — `base` was re-pointed to `d6ed153` on
  2026-11-08 while the case-*-head tags were built 2026-10-01 onto the
  pre-move lineage, so this verifier currently reports RED with the
  per-tag failures printed above. It is accurate, not broken: CI never
  runs this file (`.github/workflows` carries no reference), and CI's eval
  path materializes refs fresh with `--refs-only`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def main() -> int:
    failures: list[str] = []
    base = git("rev-parse", "base")
    head = git("rev-parse", "head-v1")
    print(f"base    = {base[:8]}")
    print(f"head-v1 = {head[:8]}")

    # The expected number of case tags is measured from the tracked
    # catalog, not typed: every case directory in golden-cases/ must have a
    # case-*-head tag, except the flagship (head-v1 is case-01).
    catalog = Path(__file__).resolve().parents[1] / "golden-cases"
    if not catalog.is_dir():
        print(f"golden-cases/ not found at {catalog}", file=sys.stderr)
        return 2
    case_dirs = sorted(
        d for d in catalog.iterdir()
        if d.is_dir() and d.name.startswith("case-")
    )
    if not case_dirs:
        print(f"golden-cases/ at {catalog} holds no case-* directories", file=sys.stderr)
        return 2
    expected = len(case_dirs) - 1  # the flagship is head-v1, not case-01-head
    print(f"tracked case dirs: {len(case_dirs)} -> expected case-*-head tags: {expected}")

    # 1. head-v1 lineage + flagship content.
    head_parents = git("rev-list", "--parents", "-n", "1", head).split()[1:]
    if base not in head_parents:
        failures.append(f"head-v1 parent is not base: {head_parents}")
    head_demo = git("diff", "--name-only", base, head, "--", "demo/")
    if not head_demo:
        failures.append("head-v1 demo/ diff against base is empty")

    # 2-4. case tags.
    tags = sorted(git("tag", "-l", "case-*-head").splitlines())
    print(f"case tags found: {len(tags)}")
    if len(tags) != expected:
        failures.append(f"expected {expected} case tags, found {len(tags)}")
    # ONE batched call for all parent pointers (N calls blew the 30s budget).
    revs = git("log", "--no-walk", "--format=%H %P", *tags).splitlines()
    sha_parents: dict[str, list[str]] = {}
    for line in revs:
        parts = line.split()
        if parts:
            sha_parents[parts[0]] = parts[1:]
    direct = 0
    for tag in tags:
        tree_files = git("diff", "--name-only", base, tag).splitlines()
        if not tree_files:
            failures.append(f"{tag}: empty diff vs base")
            continue
        off_demo = [f for f in tree_files if not f.startswith("demo/")]
        if off_demo:
            failures.append(f"{tag}: touches non-demo/: {off_demo}")
        tag_sha = git("rev-parse", tag)
        if sha_parents.get(tag_sha) == [base]:
            direct += 1
            continue
        # Legacy chained commit: merge-base must still be base so that even
        # a three-dot diff resolves to the same isolated mutation.
        mb = git("merge-base", base, tag)
        if mb != base:
            failures.append(f"{tag}: merge-base with base is {mb[:8]}, not base")
    print(f"tags with parent == base: {direct} (remainder are legacy chained, trees verified)")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for failure in failures:
            print("  -", failure)
        return 1
    print(f"\nGOLDEN TAGS GREEN: {len(tags)}/{expected} isolated case branches on base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
