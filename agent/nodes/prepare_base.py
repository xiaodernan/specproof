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

Counters (#193): ``prepare_base_runs_total`` counts every invocation and
``prepare_base_outcomes_<word>_total`` records how the attempt ended —
``prepared`` (worktree created and handed to the graph), ``safety_failed``
(the shared repo safety check refused), ``checkout_failed`` (git worktree
add exited non-zero after safety passed) or ``prepare_error`` (the git
invocation itself raised).  Every failure returns an empty workspace plus
one appended error, so the returned state cannot tell which layer refused;
the outcome word is that record.  The twin node prepare_head carries the
same closed vocabulary — the parity gate pins both declarations and both
families together.
"""
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.repo_safety import check_repo_safety
from agent.state import Phase0State
from agent.worktree_reclaimer import discard_unclaimed_workspace as _discard_workspace
from agent.worktree_reclaimer import write_worktree_marker
from observability.metrics import incr

logger = logging.getLogger(__name__)

#: The closed set of ways a prepare run can end (#193). Mirrored by the
#: parity family's regex and the behavior tests — a new word must move all
#: three together.  Word-for-word identical to the twin node's declaration
#: (agent/nodes/prepare_head.py); the parity derivation asserts equality.
PREPARE_OUTCOMES = frozenset({
    "prepared",         # worktree created and handed to the graph
    "safety_failed",    # shared repo safety check refused
    "checkout_failed",  # git worktree add exited non-zero
    "prepare_error",    # the git invocation itself raised
})


def prepare_base_node(state: Phase0State) -> dict[str, Any]:
    """Prepare the base workspace using git worktree."""
    incr("prepare_base_runs_total")
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    errors: list[str] = list(state.get("errors", []))
    job_id = str(state.get("job_id", ""))

    workspace = Path(tempfile.mkdtemp(prefix="specproof-base-"))

    report = check_repo_safety(
        repo_path=repo_path,
        ref=base_ref,
        worktree_target=workspace,
    )
    # SafetyReport.warnings carries this deployment's own admissions (an
    # un-armed containment knob on a pinned isolation plane, an ignored env
    # value).  Nothing else reads that field, so the check would pass in
    # silence; observability renders only the message, so each warning goes
    # into it verbatim.
    for warning in report.warnings:
        logger.warning("base prepare 安全披露 作业 %s: %s", job_id, warning)
    if not report.ok:
        _discard_workspace(workspace, None)
        errors.append(
            "Repository safety check failed for base prepare "
            f"({report.fail_reason}); worktree not created"
        )
        incr("prepare_base_outcomes_safety_failed_total")
        return {"base_workspace": "", "errors": errors}

    marker = write_worktree_marker(
        workspace,
        repo_path=repo_path,
        job_id=job_id,
    )

    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "worktree", "add", "--detach",
             str(workspace), base_ref],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if proc.returncode != 0:
            _discard_workspace(workspace, marker)
            errors.append(
                f"Failed to checkout base ref '{base_ref}' from {repo_path}: "
                f"{proc.stderr.strip()[:300]}"
            )
            incr("prepare_base_outcomes_checkout_failed_total")
            return {"base_workspace": "", "errors": errors}
    except Exception as e:  # noqa: BLE001
        _discard_workspace(workspace, marker)
        errors.append(f"Error preparing base workspace: {e}")
        incr("prepare_base_outcomes_prepare_error_total")
        return {"base_workspace": "", "errors": errors}

    incr("prepare_base_outcomes_prepared_total")
    return {"base_workspace": str(workspace)}


