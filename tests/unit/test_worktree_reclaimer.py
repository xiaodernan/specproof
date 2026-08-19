"""Unit tests for agent/worktree_reclaimer.py — §14.1 crash reclaimer.

Coverage: marker convention roundtrip, own-marked worktrees are reclaimed,
foreign (other-job / foreign-kind / invalid) markers are left untouched,
stale markers are cleaned, containment is enforced, and runner failures keep
the marker for retry.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from agent.worktree_reclaimer import (
    MARKER_KIND,
    MARKER_SUFFIX,
    MARKER_VERSION,
    WORKTREE_MARKER_PREFIX,
    marker_filename,
    reclaim_orphans,
    write_worktree_marker,
)


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "specproof@example.com")
    _git(root, "config", "user.name", "specproof")
    (root / "file.txt").write_text("hello\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def wt_root(tmp_path: Path) -> Path:
    root = tmp_path / "wtroot"
    root.mkdir()
    return root


def _register_worktree(repo: Path, wt_root: Path, job_id: str, name: str) -> tuple[Path, Path]:
    """Create a real registered worktree plus its sidecar marker."""
    worktree = wt_root / name
    worktree.mkdir()
    marker = write_worktree_marker(
        worktree, repo_path=repo, job_id=job_id, root=wt_root,
    )
    _git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
    return worktree, marker


class TestMarkerConvention:
    def test_marker_filename_is_deterministic_and_hashed(self, wt_root: Path) -> None:
        path = wt_root / "ws-a"
        name = marker_filename(path)
        assert name == marker_filename(path)
        assert name.startswith(WORKTREE_MARKER_PREFIX)
        assert name.endswith(MARKER_SUFFIX)
        assert marker_filename(wt_root / "ws-b") != name

    def test_write_marker_roundtrip_fields(self, repo: Path, wt_root: Path) -> None:
        worktree = wt_root / "ws"
        worktree.mkdir()
        marker = write_worktree_marker(
            worktree, repo_path=repo, job_id="job-9", root=wt_root,
        )
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["kind"] == MARKER_KIND
        assert data["version"] == MARKER_VERSION
        assert data["job_id"] == "job-9"
        assert data["worktree_path"] == str(worktree.resolve())
        assert data["repo_path"] == str(repo.resolve())
        assert "created_at" in data


class TestReclaimOwnMarked:
    def test_reclaim_removes_own_marked_worktree(
        self, repo: Path, wt_root: Path
    ) -> None:
        worktree, marker = _register_worktree(repo, wt_root, "job-a", "ws-a")
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 1
        assert result.left_foreign == 0
        assert not worktree.exists()
        assert not marker.exists()
        assert str(worktree) not in _git(repo, "worktree", "list")

    def test_reclaim_leaves_foreign_job(
        self, repo: Path, wt_root: Path
    ) -> None:
        mine, my_marker = _register_worktree(repo, wt_root, "job-a", "ws-a")
        theirs, their_marker = _register_worktree(repo, wt_root, "job-b", "ws-b")
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 1
        assert result.left_foreign == 1
        assert not mine.exists()
        assert not my_marker.exists()
        assert theirs.exists()
        assert their_marker.exists()

    def test_sweep_without_job_reclaims_all(
        self, repo: Path, wt_root: Path
    ) -> None:
        ws_a, _ = _register_worktree(repo, wt_root, "job-a", "ws-a")
        ws_b, _ = _register_worktree(repo, wt_root, "job-b", "ws-b")
        result = reclaim_orphans(wt_root, None)
        assert result.reclaimed == 2
        assert result.left_foreign == 0
        assert not ws_a.exists()
        assert not ws_b.exists()


class TestReclaimLeavesForeign:
    def test_invalid_json_marker_untouched(self, wt_root: Path) -> None:
        bogus = wt_root / (WORKTREE_MARKER_PREFIX + "deadbeef" + MARKER_SUFFIX)
        bogus.write_text("{not json", encoding="utf-8")
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 0
        assert result.warnings
        assert bogus.exists()

    def test_foreign_kind_marker_untouched(self, wt_root: Path) -> None:
        foreign = wt_root / (WORKTREE_MARKER_PREFIX + "cafebabe" + MARKER_SUFFIX)
        foreign.write_text(json.dumps({"kind": "other-tool", "version": 1}), encoding="utf-8")
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 0
        assert foreign.exists()

    def test_wrong_version_marker_untouched(self, repo: Path, wt_root: Path) -> None:
        worktree = wt_root / "ws"
        worktree.mkdir()
        marker = write_worktree_marker(
            worktree, repo_path=repo, job_id="job-a", root=wt_root,
        )
        data = json.loads(marker.read_text(encoding="utf-8"))
        data["version"] = 99
        marker.write_text(json.dumps(data), encoding="utf-8")
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 0
        assert worktree.exists()
        assert marker.exists()

    def test_marker_outside_allowed_root_untouched(
        self, repo: Path, wt_root: Path, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        marker = write_worktree_marker(
            elsewhere, repo_path=repo, job_id="job-a", root=wt_root,
        )
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 0
        assert result.failures
        assert any("outside the allowed root" in f for f in result.failures)
        assert elsewhere.exists()
        assert marker.exists()

    def test_marker_filename_mismatch_untouched(
        self, repo: Path, wt_root: Path
    ) -> None:
        worktree = wt_root / "ws"
        worktree.mkdir()
        marker = write_worktree_marker(
            worktree, repo_path=repo, job_id="job-a", root=wt_root,
        )
        renamed = wt_root / (WORKTREE_MARKER_PREFIX + "0123456789abcdef" + MARKER_SUFFIX)
        marker.rename(renamed)
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 0
        assert any("filename does not match" in w for w in result.warnings)
        assert worktree.exists()
        assert renamed.exists()


class TestReclaimEdgeCases:
    def test_stale_marker_worktree_gone(self, repo: Path, wt_root: Path) -> None:
        worktree = wt_root / "gone"
        marker = write_worktree_marker(
            worktree, repo_path=repo, job_id="job-a", root=wt_root,
        )
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 1
        assert not marker.exists()
        assert any("already gone" in w for w in result.warnings)

    def test_unregistered_empty_worktree_pruned(
        self, repo: Path, wt_root: Path
    ) -> None:
        worktree = wt_root / "ws-empty"
        worktree.mkdir()
        marker = write_worktree_marker(
            worktree, repo_path=repo, job_id="job-a", root=wt_root,
        )
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 1
        assert not worktree.exists()
        assert not marker.exists()

    def test_unregistered_nonempty_worktree_kept(
        self, repo: Path, wt_root: Path
    ) -> None:
        worktree = wt_root / "ws-dirty"
        worktree.mkdir()
        (worktree / "mystery.txt").write_text("foreign\n", encoding="utf-8")
        marker = write_worktree_marker(
            worktree, repo_path=repo, job_id="job-a", root=wt_root,
        )
        result = reclaim_orphans(wt_root, "job-a")
        assert result.reclaimed == 0
        assert result.failures
        assert worktree.exists()
        assert marker.exists()
        assert (worktree / "mystery.txt").exists()

    def test_runner_exception_keeps_marker_for_retry(
        self, repo: Path, wt_root: Path
    ) -> None:
        worktree, marker = _register_worktree(repo, wt_root, "job-a", "ws-a")

        def _boom(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
            raise RuntimeError("runner down")

        result = reclaim_orphans(wt_root, "job-a", git_runner=_boom)
        assert result.reclaimed == 0
        assert result.failures
        assert worktree.exists()
        assert marker.exists()
