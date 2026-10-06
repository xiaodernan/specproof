
"""intake node — read requirement spec and validate inputs."""
from pathlib import Path
from typing import Any

from agent.state import Phase0State
from observability.metrics import incr


def intake_node(state: Phase0State) -> dict[str, Any]:
    """Read the requirement spec file and validate git repository.

    #186: count every intake execution and its per-check validation outcomes
    at the node boundary — runs counts every execution; the repo and spec
    checks are independent, so one run can tick repo_missing AND spec_read
    (a missing repo does not stop the spec read; #186b pinned by behavior
    test). Recorded errors still abort the job at the next guard
    (graph._abort_on_preflight), which is how these counters explain jobs
    that never reach later nodes (honest attribution, not silent drops).
    """
    errors: list[str] = []
    requirement_text = ""

    # #186: count every intake execution that reaches this point
    incr("intake_runs_total")

    repo = Path(state.get("repo_path", ""))
    if not repo.exists():
        errors.append(f"Repository path does not exist: {repo}")
        # #186: repo missing — recorded error; the preflight guard aborts
        incr("intake_repo_missing_total")

    spec_path = state.get("spec_path", "")
    spec_file = Path(spec_path)
    if not spec_file.exists():
        errors.append(f"Spec file does not exist: {spec_file}")
        # #186: spec missing — recorded error; the preflight guard aborts
        incr("intake_spec_missing_total")
    else:
        requirement_text = spec_file.read_text(encoding="utf-8")
        # #186: successful spec read (no validation errors from this check)
        incr("intake_spec_read_total")

    return {
        "requirement_text": requirement_text,
        "errors": state.get("errors", []) + errors,
    }
