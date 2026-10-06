
"""intake node — read requirement spec and validate inputs."""
from pathlib import Path
from typing import Any

from agent.state import Phase0State
from observability.metrics import incr


def intake_node(state: Phase0State) -> dict[str, Any]:
    """Read the requirement spec file and validate git repository.

    #186: count every intake execution and its validation outcomes at the
    node boundary — repo missing / spec missing / success are mutually
    exclusive outcomes that together explain why a job never reaches later
    nodes (honest failure attribution, not silent drops).
    """
    errors: list[str] = []
    requirement_text = ""

    # #186: count every intake execution that reaches this point
    incr("intake_runs_total")

    repo = Path(state.get("repo_path", ""))
    if not repo.exists():
        errors.append(f"Repository path does not exist: {repo}")
        # #186: repo missing is a terminal validation failure
        incr("intake_repo_missing_total")

    spec_path = state.get("spec_path", "")
    spec_file = Path(spec_path)
    if not spec_file.exists():
        errors.append(f"Spec file does not exist: {spec_file}")
        # #186: spec missing is a terminal validation failure
        incr("intake_spec_missing_total")
    else:
        requirement_text = spec_file.read_text(encoding="utf-8")
        # #186: successful spec read (no validation errors from this check)
        incr("intake_spec_read_total")

    return {
        "requirement_text": requirement_text,
        "errors": state.get("errors", []) + errors,
    }
