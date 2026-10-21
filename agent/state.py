
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
    job_id: str  # owning job (object metadata store records it per artifact)
    use_llm: bool  # False = fully deterministic run (eval, CI)
    app_dir: str  # subdirectory inside the repo that holds pom.xml ("" = repo root)

    # ── Intermediate ──
    # Phase 1.4: environment preflight (toolchain probes). Channel, not a
    # transient: the report and the web UI read it to explain why a job
    # aborted before any evidence could be produced.
    preflight: dict[str, Any]
    requirement_text: str
    contracts: list[dict[str, Any]]
    # §14.1: full audit of the compile_contracts run — parser rule version,
    # LLM participation, rejected candidates, schema errors, degrade
    # reasons, requirement digest, duration. Channel, not a transient:
    # downstream reporting reads it to explain a small candidate set.
    compile_report: dict[str, Any]
    changed_symbols: list[str]
    # §14.1 collect_diff three scopes: file-level (audit), symbol-level
    # (retrieval/checkers) and semantic candidates (dynamic experiment +
    # mutation budget). Unparseable/binary changes stay explicit.
    changed_files: list[str]
    semantic_candidates: list[dict[str, Any]]
    unresolved_changes: list[dict[str, Any]]
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
    # The external world (Redis / MinIO) as observed at TWO moments:
    # after the Base run and after the Head run. The differential run
    # captures them; the evidence collector compares them. Two moments,
    # because one moment compared with itself always says "nothing
    # changed". Channel, not a transient: the collector node runs later.
    external_state_base: dict[str, Any]
    external_state_head: dict[str, Any]
    # Whether the external world was put back between the two runs, and
    # how many keys went. Without it, "the Head run left nothing behind"
    # and "the Head run started from a clean world" read the same.
    external_reset: dict[str, Any]
    # The evidence pack's outcome. LangGraph keeps ONLY the channels the
    # state schema declares — a node that returns an undeclared key has
    # it SILENTLY DROPPED, so "the pack was not written" would have no
    # way to reach the reader. Every key a node returns must be declared
    # here, or it does not exist.
    evidence_pack_saved: bool
    evidence_pack_error: str
    fragments_collected: int
    # Whether this run may write the evidence pack into the MongoDB audit
    # trail. The trail belongs to REAL verification jobs; an evaluation is
    # a MEASUREMENT, and its packs would be `eval-*` junk nobody can
    # delete by job id. So the default is "do not write", and the
    # operator opts in by naming the database.
    write_evidence_pack: bool
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
    # §14.1: full audit of every candidate the policy layer saw — including
    # model-ignored candidates, parse-failure outcomes (never auto-confirmed)
    # and preexisting-defect downgrades (Base also fails → NOT_ATTRIBUTED /
    # INFORMATIONAL with the Base/Head comparison recorded).
    court_audit: list[dict[str, Any]]

    # ── Output ──
    matrix: dict[str, Any]
    capsules: list[str]
    # The object-store coordinates of the capsules ("bucket/object-name").
    # Where the bytes ARE — a capsule path says only where the local
    # file was, on the machine that made it.
    capsule_refs: list[str]
    # What happened to each capsule, keyed by the contract it belongs
    # to: the address, the digest, whether an index row points at it,
    # and whether it reached the store at all. A matrix row has to be
    # able to say WHERE the evidence for THAT requirement is — and
    # whether that address is a live, findable object. A durable but
    # unindexed capsule is a different fact from a missing one.
    artifact_records_by_contract: dict[str, list[dict[str, Any]]]
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
        "job_id": "",
        "use_llm": True,
        "app_dir": "",
        "preflight": {},
        "requirement_text": "",
        "contracts": [],
        "compile_report": {},
        "changed_symbols": [],
        "changed_files": [],
        "semantic_candidates": [],
        "unresolved_changes": [],
        "base_workspace": "",
        "head_workspace": "",
        "repo_context": [],
        "retrieval_note": "",
        "approved_contracts": [],
        "require_approved_contracts": False,
        "deep_results": {},
        "deep_note": "",
        "external_state_base": {},
        "external_state_head": {},
        "external_reset": {},
        "evidence_pack_saved": False,
        "evidence_pack_error": "",
        "fragments_collected": 0,
        "write_evidence_pack": True,
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
        "court_audit": [],
        "matrix": {},
        "capsules": [],
        "capsule_refs": [],
        "artifact_records_by_contract": {},
        "certificate": None,
        "report_path": "",
        "errors": [],
        "iterations": 0,
        "max_iterations": 3,
        "messages": [],
    }
