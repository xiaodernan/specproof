"""Removing the temporary Base/Head worktrees a run created.

``eval`` and ``verify`` each carried a byte-identical copy of this loop (#496).
Both run the same pipeline and leave the same two worktrees behind, so the
cleanup is one decision: force-remove each workspace the run recorded, and
never let a cleanup failure mask the run's own result (the suppression is
deliberate — a locked worktree must not turn a finished verification into a
crash).

This is NOT the same policy as ``agent.worktree_reclaimer``'s crash reclaimer
or the prepare nodes' ``discard_unclaimed_workspace``: those handle a workspace
the graph never claimed, where deleting a non-empty tree would lose work. Here
the run is over and the worktrees are its own, so ``--force`` is correct.
"""
from __future__ import annotations

import subprocess
from contextlib import suppress
from typing import Any


def cleanup_run_worktrees(repo: str, final: dict[str, Any]) -> None:
    """Force-remove the ``base_workspace`` / ``head_workspace`` a run recorded."""
    for key in ("base_workspace", "head_workspace"):
        workspace = final.get(key, "")
        if not workspace:
            continue
        with suppress(Exception):
            subprocess.run(
                ["git", "-C", repo, "worktree", "remove", "--force", workspace],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )


__all__ = ["cleanup_run_worktrees"]
