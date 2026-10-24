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


def walk_files(root: str | Path, exts: frozenset[str]) -> list[tuple[Path, str]]:
    """``(path, relative)`` for every file under ``root`` with a suffix in ``exts``.

    One pruned walk instead of one ``rglob`` per pattern: the excluded
    directories are never descended into, which is what makes scanning the whole
    project tree affordable instead of minutes-long.
    """
    out: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fname in sorted(filenames):
            if os.path.splitext(fname)[1].lower() not in exts:
                continue
            fpath = Path(dirpath, fname)
            out.append((fpath, str(fpath.relative_to(root)).replace("\\", "/")))
    return out
