
"""prepare_base node — checkout the base ref into an isolated workspace.

Uses subprocess with argument lists (no shell interpolation), so repo paths
and refs coming from untrusted job payloads cannot inject commands.
"""
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.state import Phase0State


def prepare_base_node(state: Phase0State) -> dict[str, Any]:
    """Prepare the base workspace using git worktree."""
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "base")
    errors: list[str] = list(state.get("errors", []))

    workspace = Path(tempfile.mkdtemp(prefix="specproof-base-"))

    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "worktree", "add", "--detach",
             str(workspace), base_ref],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            errors.append(
                f"Failed to checkout base ref '{base_ref}' from {repo_path}: "
                f"{proc.stderr.strip()[:300]}"
            )
            return {"base_workspace": "", "errors": errors}
    except Exception as e:  # noqa: BLE001
        errors.append(f"Error preparing base workspace: {e}")
        return {"base_workspace": "", "errors": errors}

    return {"base_workspace": str(workspace)}
