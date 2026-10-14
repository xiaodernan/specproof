"""`_cleanup_worktrees` must never crash the run (#246-era robustness).

When a case's differential leaves a git worktree behind, `eval_cmd` asks
`_cleanup_worktrees` to remove it. A failed removal (locked worktree, missing
path, already gone) must NOT turn into a traceback that loses the result the
pipeline already produced -- so every removal is wrapped in
`suppress(Exception)`. These tests pin that contract with a real worktree.

Run via direct invocation below (bypasses pytest's teardown safe-delete guard).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.specproof.commands.eval import _cleanup_worktrees  # noqa: E402


def _make_repo_with_worktree(d: Path):
    repo = d / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "tester"], check=True
    )
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    wt = d / "wt"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", str(wt), "HEAD"], check=True
    )
    return repo, wt


def _cleanup_skips_empty_workspace(d: Path, mp) -> None:
    repo = d / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    # No base_workspace / head_workspace -> loop body never touches git.
    assert _cleanup_worktrees(str(repo), {}) is None


def _cleanup_missing_workspace_does_not_raise(d: Path, mp) -> None:
    repo = d / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    # A path that does not exist: `git worktree remove` fails, suppress swallows it.
    _cleanup_worktrees(str(repo), {"base_workspace": str(d / "nope")})


def _cleanup_removes_existing_worktree(d: Path, mp) -> None:
    repo, wt = _make_repo_with_worktree(d)
    assert wt.exists(), "worktree should exist before cleanup"
    _cleanup_worktrees(str(repo), {"base_workspace": str(wt)})
    # --force removal should have taken the working dir away.
    assert not wt.exists(), "worktree should be removed after cleanup"


def test_cleanup_skips_empty_workspace(tmp_path, monkeypatch):
    _cleanup_skips_empty_workspace(tmp_path, monkeypatch)


def test_cleanup_missing_workspace_does_not_raise(tmp_path, monkeypatch):
    _cleanup_missing_workspace_does_not_raise(tmp_path, monkeypatch)


def test_cleanup_removes_existing_worktree(tmp_path, monkeypatch):
    _cleanup_removes_existing_worktree(tmp_path, monkeypatch)


if __name__ == "__main__":
    from _pytest.monkeypatch import MonkeyPatch

    tests = [
        _cleanup_skips_empty_workspace,
        _cleanup_missing_workspace_does_not_raise,
        _cleanup_removes_existing_worktree,
    ]
    failures = 0
    for fn in tests:
        base = Path(tempfile.mkdtemp(prefix="clnwt-"))
        mp = MonkeyPatch()
        try:
            fn(base, mp)
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL", fn.__name__, "->", type(exc).__name__, str(exc)[:300])
        finally:
            mp.undo()
        # deliberately NOT deleting base: safe-delete guard hangs on bulk delete
    print("RESULT:", "ALL PASS" if failures == 0 else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
