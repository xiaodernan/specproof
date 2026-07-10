"""intake node — read requirement spec and validate inputs."""

from pathlib import Path

from agent.state import Phase0State


def intake_node(state: Phase0State) -> dict:
    """Read the requirement spec file and validate git repository."""
    errors: list[str] = []
    requirement_text = ""

    repo = Path(state.get("repo_path", ""))
    if not repo.exists():
        errors.append(f"Repository path does not exist: {repo}")

    spec_path = state.get("spec_path", "")
    spec_file = Path(spec_path)
    if not spec_file.exists():
        errors.append(f"Spec file does not exist: {spec_file}")
    else:
        requirement_text = spec_file.read_text(encoding="utf-8")

    return {
        "requirement_text": requirement_text,
        "errors": state.get("errors", []) + errors,
    }
