"""prepare_head node — checkout the head ref into an isolated workspace."""

import os
import uuid

from agent.state import Phase0State


def prepare_head_node(state: Phase0State) -> dict:
    """Prepare the head workspace using git worktree or clone."""
    repo_path = state.get("repo_path", "")
    head_ref = state.get("head_ref", "head-v1")
    errors: list[str] = []

    workspace_id = str(uuid.uuid4())[:8]
    head_workspace = os.path.join(
        os.environ.get("TEMP", "/tmp"),
        f"specproof-head-{workspace_id}",
    )

    try:
        result = os.system(
            f'git -C "{repo_path}" worktree add "{head_workspace}" {head_ref} '
            f'2>nul'
        )
        if result != 0:
            os.makedirs(head_workspace, exist_ok=True)
            result2 = os.system(
                f'git -C "{repo_path}" --work-tree="{head_workspace}" '
                f'checkout {head_ref} -- . 2>nul'
            )
            if result2 != 0:
                errors.append(
                    f"Failed to checkout head ref '{head_ref}' "
                    f"from {repo_path}"
                )
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
