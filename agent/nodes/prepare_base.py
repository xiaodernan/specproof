"""prepare_base node — checkout the base ref into an isolated workspace."""

import os
import subprocess
import tempfile
import uuid

from agent.state import Phase0State


def prepare_base_node(state: Phase0State) -> dict:
    """Prepare the base workspace using git worktree or clone.

    For Phase 0 on Windows, uses a lightweight approach:
    create a temp directory and copy/checkout the base ref.
    """
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    errors: list[str] = []

    workspace_id = str(uuid.uuid4())[:8]
    base_workspace = os.path.join(
        tempfile.gettempdir(),
        f"specproof-base-{workspace_id}",
    )

    try:
        # Use git worktree if possible (subprocess avoids shell injection)
        result = subprocess.run(
            ["git", "-C", repo_path, "worktree", "add", base_workspace, base_ref],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Fallback: checkout branch directly
            os.makedirs(base_workspace, exist_ok=True)
            result2 = subprocess.run(
                [
                    "git",
                    "-C",
                    repo_path,
                    f"--work-tree={base_workspace}",
                    "checkout",
                    base_ref,
                    "--",
                    ".",
                ],
                capture_output=True,
                timeout=30,
            )
            if result2.returncode != 0:
                errors.append(f"Failed to checkout base ref '{base_ref}' from {repo_path}")
                return {
                    "base_workspace": "",
                    "errors": state.get("errors", []) + errors,
                }
    except Exception as e:
        errors.append(f"Error preparing base workspace: {e}")
        return {
            "base_workspace": "",
            "errors": state.get("errors", []) + errors,
        }

    return {"base_workspace": base_workspace}
