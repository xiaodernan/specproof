"""prepare_head node — checkout the head ref into an isolated workspace."""

import os
import subprocess
import tempfile
import uuid

from agent.state import Phase0State


def prepare_head_node(state: Phase0State) -> dict:
    """Prepare the head workspace using git worktree or clone."""
    repo_path = state.get("repo_path", "")
    head_ref = state.get("head_ref", "head-v1")
    errors: list[str] = []

    workspace_id = str(uuid.uuid4())[:8]
    head_workspace = os.path.join(
        tempfile.gettempdir(),
        f"specproof-head-{workspace_id}",
    )

    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "worktree", "add", head_workspace, head_ref],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            os.makedirs(head_workspace, exist_ok=True)
            result2 = subprocess.run(
                [
                    "git",
                    "-C",
                    repo_path,
                    f"--work-tree={head_workspace}",
                    "checkout",
                    head_ref,
                    "--",
                    ".",
                ],
                capture_output=True,
                timeout=30,
            )
            if result2.returncode != 0:
                errors.append(f"Failed to checkout head ref '{head_ref}' from {repo_path}")
                return {
                    "head_workspace": "",
                    "errors": state.get("errors", []) + errors,
                }
    except Exception as e:
        errors.append(f"Error preparing head workspace: {e}")
        return {
            "head_workspace": "",
            "errors": state.get("errors", []) + errors,
        }

    return {"head_workspace": head_workspace}
