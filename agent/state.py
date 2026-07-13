"""SpecProof Phase 0 Agent — LangGraph state definition."""

from langgraph.graph import MessagesState


class Phase0State(MessagesState):
    """State carried through the Phase 0 verification graph.

    Extends MessagesState for LangGraph message tracking.
    All nodes read and write this shared state.
    """

    # ── Input ──
    repo_path: str
    base_ref: str
    head_ref: str
    spec_path: str
    depth: str  # "FAST" only in Phase 0

    # ── Intermediate ──
    requirement_text: str
    contracts: list[dict]
    changed_symbols: list[str]
    base_workspace: str
    head_workspace: str

    # ── Tool outputs ──
    static_findings: list[dict]
    diff_results: list[dict]
    generated_tests_path: str

    # ── Review Court ──
    candidate_findings: list[dict]
    confirmed_findings: list[dict]

    # ── Output ──
    matrix: dict
    capsules: list[str]
    certificate: dict | None
    report_path: str

    # ── Control ──
    errors: list[str]
    iterations: int
    max_iterations: int


def initial_state(
    repo_path: str,
    base_ref: str,
    head_ref: str,
    spec_path: str,
    depth: str = "FAST",
) -> Phase0State:
    return {
        "repo_path": repo_path,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "spec_path": spec_path,
        "depth": depth,
        "requirement_text": "",
        "contracts": [],
        "changed_symbols": [],
        "base_workspace": "",
        "head_workspace": "",
        "static_findings": [],
        "diff_results": [],
        "generated_tests_path": "",
        "candidate_findings": [],
        "confirmed_findings": [],
        "matrix": {},
        "capsules": [],
        "certificate": None,
        "report_path": "",
        "errors": [],
        "iterations": 0,
        "max_iterations": 3,
        "messages": [],
    }
