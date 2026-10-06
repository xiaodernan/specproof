"""prepare_head node — checkout the head ref into an isolated workspace.

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

Counters (#193): the twin of prepare_base's — ``prepare_head_runs_total``
counts every invocation and ``prepare_head_outcomes_<word>_total`` records
how the attempt ended through the same four-word closed vocabulary
(PREPARE_OUTCOMES: prepared / safety_failed / checkout_failed /
prepare_error).  One job mounts two worktrees, so counting both nodes
separately shows which half failed; the empty-workspace return shape is
identical for every failure, so the outcome word is the record of what
refused.  The parity derivation asserts this declaration stays
word-for-word equal to the twin's.
"""
import contextlib
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.repo_safety import check_repo_safety
from agent.state import Phase0State
from agent.worktree_reclaimer import write_worktree_marker
from observability.metrics import incr

logger = logging.getLogger(__name__)

#: The closed set of ways a prepare run can end (#193). Mirrored by the
#: parity family's regex and the behavior tests — a new word must move all
#: three together.  Word-for-word identical to the twin node's declaration
#: (agent/nodes/prepare_base.py); the parity derivation asserts equality.
PREPARE_OUTCOMES = frozenset({
    "prepared",         # worktree created and handed to the graph
    "safety_failed",    # shared repo safety check refused
    "checkout_failed",  # git worktree add exited non-zero
    "prepare_error",    # the git invocation itself raised
})


def prepare_head_node(state: Phase0State) -> dict[str, Any]:
    """Prepare the head workspace using git worktree."""
    incr("prepare_head_runs_total")
    repo_path = state.get("repo_path", "")
    head_ref = state.get("head_ref", "head-v1")
    errors: list[str] = list(state.get("errors", []))
    job_id = str(state.get("job_id", ""))

    workspace = Path(tempfile.mkdtemp(prefix="specproof-head-"))

    report = check_repo_safety(
        repo_path=repo_path,
        ref=head_ref,
        worktree_target=workspace,
    )
    # The counterpart of the base node's disclosure: a job mounts two
    # worktrees into the same container, so both halves must state the
    # containment gap.  observability renders only the message.
    for warning in report.warnings:
        logger.warning("head prepare 安全披露 作业 %s: %s", job_id, warning)
    if not report.ok:
        _discard_workspace(workspace, None)
        errors.append(
            "Repository safety check failed for head prepare "
            f"({report.fail_reason}); worktree not created"
        )
        incr("prepare_head_outcomes_safety_failed_total")
        return {"head_workspace": "", "errors": errors}

    marker = write_worktree_marker(
        workspace,
        repo_path=repo_path,
        job_id=job_id,
    )

    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "worktree", "add", "--detach",
             str(workspace), head_ref],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if proc.returncode != 0:
            _discard_workspace(workspace, marker)
            errors.append(
                f"Failed to checkout head ref '{head_ref}' from {repo_path}: "
                f"{proc.stderr.strip()[:300]}"
            )
            incr("prepare_head_outcomes_checkout_failed_total")
            return {"head_workspace": "", "errors": errors}
    except Exception as e:  # noqa: BLE001
        _discard_workspace(workspace, marker)
        errors.append(f"Error preparing head workspace: {e}")
        incr("prepare_head_outcomes_prepare_error_total")
        return {"head_workspace": "", "errors": errors}

    incr("prepare_head_outcomes_prepared_total")
    return {"head_workspace": str(workspace)}


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
