"""prepare_base node — checkout the base ref into an isolated workspace.

Before any worktree operation the node runs the shared repository safety
checks (agent/repo_safety.py, §14.1): path containment, ref membership,
worktree target state, symlink escape, repo size, forbidden files and the
execution-mode signal.  A failed check aborts the node with an error naming
the failing check; when every check passes the git behaviour is identical to
the pre-extraction node (same argument list, no shell interpolation, so
paths and refs from untrusted job payloads cannot inject commands).

The workspace is registered with a sidecar marker file
(agent/worktree_reclaimer.py) before 'git worktree add', so a crash between
registration and cleanup leaves a reclaimable claim behind.
"""
import contextlib
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.repo_safety import check_repo_safety
from agent.state import Phase0State
from agent.worktree_reclaimer import write_worktree_marker


def prepare_base_node(state: Phase0State) -> dict[str, Any]:
    """Prepare the base workspace using git worktree."""
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    errors: list[str] = list(state.get("errors", []))

    workspace = Path(tempfile.mkdtemp(prefix="specproof-base-"))

    report = check_repo_safety(
        repo_path=repo_path,
        ref=base_ref,
        worktree_target=workspace,
    )
    if not report.ok:
        _discard_workspace(workspace, None)
        errors.append(
            "Repository safety check failed for base prepare "
            f"({report.fail_reason}); worktree not created"
        )
        return {"base_workspace": "", "errors": errors}

    marker = write_worktree_marker(
        workspace,
        repo_path=repo_path,
        job_id=str(state.get("job_id", "")),
    )

    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "worktree", "add", "--detach",
             str(workspace), base_ref],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            _discard_workspace(workspace, marker)
            errors.append(
                f"Failed to checkout base ref '{base_ref}' from {repo_path}: "
                f"{proc.stderr.strip()[:300]}"
            )
            return {"base_workspace": "", "errors": errors}
    except Exception as e:  # noqa: BLE001
        _discard_workspace(workspace, marker)
        errors.append(f"Error preparing base workspace: {e}")
        return {"base_workspace": "", "errors": errors}

    return {"base_workspace": str(workspace)}


def _discard_workspace(workspace: Path, marker: Path | None) -> None:
    """Best-effort cleanup of a workspace that was never handed to the graph.

    An empty directory is removed immediately; the marker is dropped only
    once the directory is gone, so a non-empty leftover keeps its claim and
    stays reclaimable by the worker's crash reclaimer.
    """
    if workspace.is_dir():
        with contextlib.suppress(OSError):
            workspace.rmdir()
    if marker is not None and not workspace.exists():
        with contextlib.suppress(OSError):
            marker.unlink()
