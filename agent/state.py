
"""SpecProof Phase 0 Agent — LangGraph state definition."""
from typing import Any

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
    output_dir: str  # where the verification report is written
    use_llm: bool  # False = fully deterministic run (eval, CI)
    app_dir: str  # subdirectory inside the repo that holds pom.xml ("" = repo root)

    # ── Intermediate ──
    requirement_text: str
    contracts: list[dict[str, Any]]
    changed_symbols: list[str]
    base_workspace: str
    head_workspace: str
    # P2: repository context retrieved from Elasticsearch (symbol chunks)
    repo_context: list[dict[str, Any]]
    retrieval_note: str
    # P2: registry-approved contracts (empty = implicit spec compilation)
    approved_contracts: list[dict[str, Any]]
    require_approved_contracts: bool
    # P3/P4: DEEP tier experiment results (mutation + full-stack deltas)
    deep_results: dict[str, Any]
    deep_note: str
    # P5: RELEASE tier gates (reproducibility + capsule integrity)
    release_results: dict[str, Any]
    release_note: str

    # ── Tool outputs ──
    static_findings: list[dict[str, Any]]
    diff_results: list[dict[str, Any]]
    generated_tests_path: str
    # Full record of test generation (source: llm_generated |
    # deterministic_template, attempts, compile result). Channel, not a
    # transient: run_differential reads it to label evidence honestly.
    generation_record: dict[str, Any]
    # Per-file unified diffs (path -> diff text) collected from Base/Head;
    # the worker consumes it to anchor GitHub Inline Findings. Channel,
    # not a transient: without it the graph silently drops the node output
    # and the worker's inline-finding path can never see real diffs.
    diff_by_file: dict[str, str]
    # Per-contract experiment results (only real experiments may set PASS/FAIL).
    contract_results: list[dict[str, Any]]

    # ── Review Court ──
    candidate_findings: list[dict[str, Any]]
    confirmed_findings: list[dict[str, Any]]

    # ── Output ──
    matrix: dict[str, Any]
    capsules: list[str]
    certificate: dict[str, Any] | None
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
        "output_dir": "reports",
        "use_llm": True,
        "app_dir": "",
        "requirement_text": "",
        "contracts": [],
        "changed_symbols": [],
        "base_workspace": "",
        "head_workspace": "",
        "repo_context": [],
        "retrieval_note": "",
        "approved_contracts": [],
        "require_approved_contracts": False,
        "deep_results": {},
        "deep_note": "",
        "release_results": {},
        "release_note": "",
        "static_findings": [],
        "diff_results": [],
        "generated_tests_path": "",
        "generation_record": {},
        "diff_by_file": {},
        "contract_results": [],
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
