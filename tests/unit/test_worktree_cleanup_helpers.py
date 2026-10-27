"""#496 — the two worktree-cleanup helpers, pinned directly.

Two different policies share the word "cleanup" and must not be confused:

* ``discard_unclaimed_workspace`` (prepare nodes) only removes an **empty**
  directory and keeps the marker when anything is left, so the worker's crash
  reclaimer can still take it — deleting a non-empty tree here would lose work.
* ``cleanup_run_worktrees`` (eval / verify CLI) force-removes the worktrees the
  run itself created, and swallows failures so a locked worktree cannot turn a
  finished verification into a crash.

Both were duplicated before (#496); each gets its own tests now.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import cli.specproof.commands._worktrees as worktrees
from agent.worktree_reclaimer import discard_unclaimed_workspace

# ── discard_unclaimed_workspace: never delete work ─────────────────────


def test_an_empty_workspace_and_its_marker_are_removed(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    marker = tmp_path / "ws.marker"
    marker.write_text("{}", encoding="utf-8")

    discard_unclaimed_workspace(workspace, marker)

    assert not workspace.exists()
    assert not marker.exists()


def test_a_non_empty_workspace_keeps_both_the_directory_and_the_marker(
    tmp_path: Path,
) -> None:
    # The marker is the reclaimer's claim; dropping it while files remain would
    # strand the worktree forever.
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "leftover.txt").write_text("work", encoding="utf-8")
    marker = tmp_path / "ws.marker"
    marker.write_text("{}", encoding="utf-8")

    discard_unclaimed_workspace(workspace, marker)

    assert workspace.exists()
    assert marker.exists()


def test_a_vanished_workspace_still_drops_its_marker(tmp_path: Path) -> None:
    workspace = tmp_path / "never-created"
    marker = tmp_path / "ws.marker"
    marker.write_text("{}", encoding="utf-8")

    discard_unclaimed_workspace(workspace, marker)

    assert not marker.exists()


def test_no_marker_is_not_an_error(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    discard_unclaimed_workspace(workspace, None)
    assert not workspace.exists()


# ── cleanup_run_worktrees: force-remove what the run created ────────────


def test_both_recorded_workspaces_are_force_removed(monkeypatch: Any) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        calls.append(cmd)
        return None

    monkeypatch.setattr(worktrees.subprocess, "run", fake_run)
    worktrees.cleanup_run_worktrees(
        "/repo", {"base_workspace": "/tmp/b", "head_workspace": "/tmp/h"}
    )

    assert calls == [
        ["git", "-C", "/repo", "worktree", "remove", "--force", "/tmp/b"],
        ["git", "-C", "/repo", "worktree", "remove", "--force", "/tmp/h"],
    ]


def test_blank_or_missing_workspaces_run_nothing(monkeypatch: Any) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        worktrees.subprocess, "run", lambda cmd, **kw: calls.append(cmd)
    )

    worktrees.cleanup_run_worktrees("/repo", {"base_workspace": "", "head_workspace": ""})
    worktrees.cleanup_run_worktrees("/repo", {})

    assert calls == []


def test_a_failing_removal_never_escapes(monkeypatch: Any) -> None:
    # A locked worktree must not turn a finished run into a crash.
    def boom(cmd: list[str], **kwargs: Any) -> Any:
        raise RuntimeError("worktree is locked")

    monkeypatch.setattr(worktrees.subprocess, "run", boom)
    worktrees.cleanup_run_worktrees("/repo", {"base_workspace": "/tmp/b"})
