"""Shared full-tree walk for the scanning gates.

``tests/security`` (secret scanning) and ``tests/unit`` (product-file
population) both walk the whole project tree. Each used to carry its own exclude
list, and each list was wrong in a different way: one omitted ``.mypy_cache``
and ``.scratch`` (measured: 11,211 of the 12,394 ``*.json`` files a naive walk
reads, which made a gate hang for minutes), the other walked 27,656 ``*.py``
files to keep 7,278. Two hand-written lists about the same machine is exactly
the drift this repo fences against elsewhere, so the walk lives here once.

#541 found the second half of the same disease: a census needs *roots* as well
as excludes, and nine gates each typed their own production plane — the two
demo-marker gates disagreed with each other (13 roots vs 14, the difference
being ``experiments``) and neither opened ``mcp``, ``ops``, ``devtools`` or
``plugins``, which is the set a "there is exactly one copy of this predicate in
the product" claim has to read. One of them also tested the exclusion against
absolute path parts, so the same rule that returned 302 modules in a normal
checkout returned **0** in a worktree nested under ``.scratch`` — and an empty
census makes every absence-shaped leg pass. The roots therefore live here too,
derived from the index and floored.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

#: Directory names a full-tree scan never descends into: local virtualenvs,
#: tool caches and scratch worktrees. None of them can be committed —
#: ``.scratch`` is already ruff-excluded, the caches are gitignored — so
#: scanning them costs minutes and guards nothing.
PRUNE_DIRS = frozenset({
    ".git", "__pycache__", "target", "node_modules", ".mvn", ".local",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".scratch",
})

#: Names that are a *family*, not a single directory: a virtualenv is called
#: whatever its creator was called, so ``.venv``, ``.venv312`` and ``.venv-py312``
#: are the same kind of thing. ``agent/security_scanner._EXCLUDE_DIR_PREFIXES``
#: adopted this rule after #441 listed exact names only and #443 measured that the
#: list missed this tree's ``.venv312`` — 11,090 walked files instead of 3,023, with
#: 67 CRITICAL/HIGH findings that all lived inside the venv. The shared walk was
#: written afterwards and carried the pre-#443 exact-name list, which is how a third
#: copy of one policy drifts. Measured with the two rules on the same working copy (only
#: ``.git``/``.scratch`` held back, so a live arm worktree cannot move the count, and a
#: tree that has this project's own ``.venv312`` — a fresh checkout of a commit has no
#: venv and cannot show the hole at all):
#: exact names walked 7,341 ``*.py`` files with 6,141 of them under ``.venv312/``;
#: this rule walked 1,200 and none. Re-measured at shipping time the same pair is
#: 7,343 / 1,202, because other lanes' files move the population and only the *ratio* is
#: the finding. ``tests/_import_graph.py`` built its first graph on the 7,341.
_PRUNE_PREFIXES = (".venv",)


def pruned_dir(name: str) -> bool:
    """Whether a directory of this ``name`` is never part of the scanned tree.

    The leading dot is load-bearing: ``.venv`` as a prefix stands for the venv family
    while leaving a real ``.venue/`` or ``vendor/`` in the tree — the same reason
    #443 gave on the scanner side.
    """
    return name in PRUNE_DIRS or name.startswith(_PRUNE_PREFIXES)



def walk_files(root: str | Path, exts: frozenset[str]) -> list[tuple[Path, str]]:
    """``(path, relative)`` for every file under ``root`` with a suffix in ``exts``.

    One pruned walk instead of one ``rglob`` per pattern: the excluded
    directories are never descended into, which is what makes scanning the whole
    project tree affordable instead of minutes-long.
    """
    out: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not pruned_dir(d)]
        for fname in sorted(filenames):
            if os.path.splitext(fname)[1].lower() not in exts:
                continue
            fpath = Path(dirpath, fname)
            out.append((fpath, str(fpath.relative_to(root)).replace("\\", "/")))
    return out


#: Top-level roots that hold no product decision to census. ``tests`` is 517
#: modules whose entire job is to spell something a second time, and ``bench``
#: is 368 harnesses; counting either into a "how many copies are there" census
#: reports fakes as duplication. #541 measured both counts on this working copy.
NON_PRODUCT_ROOTS = frozenset({"tests", "bench"})

#: #516's floor, lifted here so every census shares it: below this the root
#: list is not narrow, it is broken.
_MIN_TRACKED_ROOTS = 15

#: The smallest census a product-plane scan may report and still be believed.
#: #525 typed 250 against its own 14-root list; #541 measured the derived plane
#: at 317 modules, so the floor sits where a collapsed walk cannot hide behind it.
_MIN_PRODUCT_FILES = 250


@lru_cache(maxsize=8)
def tracked_python_roots(repo: Path) -> frozenset[str]:
    """Every top-level directory that holds tracked Python.

    From the index rather than the filesystem: an untracked scratch directory
    is not a product root, and a root nobody remembered to type is exactly what
    this returns.
    """
    proc = subprocess.run(
        ("git", "ls-files", "*.py"),
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
        encoding="utf-8",
    )
    roots = {line.split("/", 1)[0] for line in proc.stdout.splitlines() if "/" in line}
    assert len(roots) >= _MIN_TRACKED_ROOTS, f"root census collapsed: {sorted(roots)}"
    return frozenset(roots)


def product_roots(repo: Path) -> frozenset[str]:
    """The plane a product census reads: tracked Python roots, minus the two that
    hold no product decision."""
    roots = tracked_python_roots(repo) - NON_PRODUCT_ROOTS
    assert roots, "no product root left after the classification"
    return roots


def product_python_files(repo: str | Path) -> list[tuple[Path, str]]:
    """``(path, relative)`` for every product module, derived and geography-proof.

    Three properties a hand-typed plane cannot hold at once, each added because
    #541 measured the failure:

    * the roots come from ``git ls-files``, so a package cannot be forgotten the
      way ``PRODUCTION_DIRS`` forgot ``experiments``, ``mcp``, ``ops``,
      ``devtools`` and ``plugins``;
    * the exclusion test reads the path **below** the walk root, because the
      same rule applied to absolute parts returned 302 modules in a normal
      checkout and **0** in a worktree nested under ``.scratch`` — which is
      where every lane's arms run;
    * the result is floored, so an empty census can never let a
      "there is exactly one copy" leg pass quietly.
    """
    root = Path(repo)
    roots = product_roots(root)
    rows = sorted(
        (
            (path, rel)
            for path, rel in walk_files(root, frozenset({".py"}))
            if rel.split("/", 1)[0] in roots
        ),
        key=lambda row: row[1],
    )
    assert len(rows) >= _MIN_PRODUCT_FILES, (
        f"only {len(rows)} product modules found over roots {sorted(roots)} — "
        f"the walk, not the code, is broken"
    )
    return rows
