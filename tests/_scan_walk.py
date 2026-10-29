"""Shared full-tree walk for the scanning gates.

``tests/security`` (secret scanning) and ``tests/unit`` (product-file
population) both walk the whole project tree. Each used to carry its own exclude
list, and each list was wrong in a different way: one omitted ``.mypy_cache``
and ``.scratch`` (measured: 11,211 of the 12,394 ``*.json`` files a naive walk
reads, which made a gate hang for minutes), the other walked 27,656 ``*.py``
files to keep 7,278. Two hand-written lists about the same machine is exactly
the drift this repo fences against elsewhere, so the walk lives here once.
"""

from __future__ import annotations

import os
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
