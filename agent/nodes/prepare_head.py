
"""prepare_head node — checkout the head ref into an isolated workspace.

Uses subprocess with argument lists (no shell interpolation), so repo paths
and refs coming from untrusted job payloads cannot inject commands.
"""
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.state import Phase0State


def prepare_head_node(state: Phase0State) -> dict[str, Any]:
    """Prepare the head workspace using git worktree."""
    repo_path = state.get("repo_path", "")
    head_ref = state.get("head_ref", "head-v1")
    errors: list[str] = list(state.get("errors", []))

    workspace = Path(tempfile.mkdtemp(prefix="specproof-head-"))

    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "worktree", "add", "--detach",
             str(workspace), head_ref],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            errors.append(
                f"Failed to checkout head ref '{head_ref}' from {repo_path}: "
                f"{proc.stderr.strip()[:300]}"
            )
            return {"head_workspace": "", "errors": errors}
    except Exception as e:  # noqa: BLE001
        errors.append(f"Error preparing head workspace: {e}")
        return {"head_workspace": "", "errors": errors}

    return {"head_workspace": str(workspace)}
