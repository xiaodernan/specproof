"""prepare_base node — checkout the base ref into an isolated workspace."""

import os
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
        os.environ.get("TEMP", "/tmp"),
        f"specproof-base-{workspace_id}",
    )

    try:
        # Use git worktree if possible
        result = os.system(
            f'git -C "{repo_path}" worktree add "{base_workspace}" {base_ref} '
            f'2>nul'
        )
        if result != 0:
            # Fallback: use git archive or clone branch
            os.makedirs(base_workspace, exist_ok=True)
            result2 = os.system(
                f'git -C "{repo_path}" --work-tree="{base_workspace}" '
                f'checkout {base_ref} -- . 2>nul'
            )
            if result2 != 0:
                errors.append(
                    f"Failed to checkout base ref '{base_ref}' "
                    f"from {repo_path}"
                )
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
