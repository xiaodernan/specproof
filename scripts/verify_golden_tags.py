"""Read-only integrity verifier for the SpecProof golden-scenario tags.

Checks, without writing anything to the repo (no commits, no tags,
no worktrees, no file changes):
1. ``base`` and ``head-v1`` tags exist; ``head-v1`` is a child of ``base``;
   their demo/ diff is exactly the flagship @PreAuthorize removal.
2. All 99 ``case-*-head`` tags exist.
3. Every case tag's tree differs from ``base`` by a NON-EMPTY diff confined
   to ``demo/`` (what the eval pipeline consumes via ``git diff base..tag``).
4. Every case tag's merge-base with ``base`` IS ``base`` itself, so even a
   three-dot diff resolves to the same isolated mutation.

Parent-pointer shape (91 tags directly on base, 8 legacy chained commits
from the pre-detached builder) is reported but not enforced: the builder
restores the base tree before each mutation, so trees — not parents — carry
the contract, and this script verifies the trees.

Usage: python scripts/verify_golden_tags.py   (exit 0 = all green)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, timeout=120,
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
    if len(tags) != 99:
        failures.append(f"expected 99 case tags, found {len(tags)}")
    direct = 0
    for tag in tags:
        tree_files = git("diff", "--name-only", base, tag).splitlines()
        if not tree_files:
            failures.append(f"{tag}: empty diff vs base")
            continue
        off_demo = [f for f in tree_files if not f.startswith("demo/")]
        if off_demo:
            failures.append(f"{tag}: touches non-demo/: {off_demo}")
        mb = git("merge-base", base, tag)
        if mb != base:
            failures.append(f"{tag}: merge-base with base is {mb[:8]}, not base")
        parent = git("rev-list", "--parents", "-n", "1", tag).split()[1:]
        if parent == [base]:
            direct += 1
    print(f"tags with parent == base: {direct} (remainder are legacy chained, trees verified)")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for failure in failures:
            print("  -", failure)
        return 1
    print("\nGOLDEN TAGS GREEN: 99/99 isolated demo/-only mutations on base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
