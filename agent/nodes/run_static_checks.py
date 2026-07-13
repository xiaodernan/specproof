"""run_static_checks node — run deterministic checks on changed code."""

import os
import re
from pathlib import Path

from agent.state import Phase0State


def run_static_checks_node(state: Phase0State) -> dict:
    """Run static analysis on the head workspace.

    Phase 0 uses regex-based checks instead of Semgrep
    to avoid external tool dependencies.
    """
    changed_symbols = state.get("changed_symbols", [])
    head_workspace = state.get("head_workspace", "")
    static_findings: list[dict] = []

    # Check 1: Detect @PreAuthorize removal
    auth_removed = any(
        "@PreAuthorize" in sym or "PreAuthorize" in sym
        for sym in changed_symbols
        if "REMOVED" in sym or "ANNOTATION_REMOVED" in sym
    )
    if auth_removed:
        static_findings.append(
            {
                "id": "STATIC-AUTH-01",
                "contract_id": "AUTH-01",
                "severity": "BLOCKER",
                "type": "annotation_removed",
                "description": "@PreAuthorize removed from controller method",
                "evidence_type": "static_analysis",
                "confidence": 0.95,
            }
        )

    # Check 2: Detect @Transactional removal
    tx_removed = any(
        "@Transactional" in sym for sym in changed_symbols if "ANNOTATION_REMOVED" in sym
    )
    if tx_removed:
        static_findings.append(
            {
                "id": "STATIC-TX-01",
                "contract_id": "TRANSACTION-01",
                "severity": "MAJOR",
                "type": "annotation_removed",
                "description": "@Transactional removed — potential data inconsistency",
                "evidence_type": "static_analysis",
                "confidence": 0.88,
            }
        )

    # Check 3: Scan head workspace controller for missing security annotations
    if head_workspace:
        for root, _dirs, files in os.walk(head_workspace):
            for fname in files:
                if fname.endswith("Controller.java") and "test" not in root.lower():
                    fpath = os.path.join(root, fname)
                    try:
                        content = Path(fpath).read_text(encoding="utf-8")
                    except Exception:
                        continue

                    # Look for @PutMapping / @PostMapping / @DeleteMapping without @PreAuthorize
                    mutating = re.findall(
                        r"(@PutMapping|@PostMapping|@DeleteMapping)\([^)]*\)\n\s*public",
                        content,
                    )
                    if mutating:
                        # Check if @PreAuthorize exists before each mutation
                        for m in mutating:
                            idx = content.find(m)
                            snippet = content[max(0, idx - 80) : idx]
                            if "@PreAuthorize" not in snippet and "@Secured" not in snippet:
                                static_findings.append(
                                    {
                                        "id": (f"STATIC-MUT-{len(static_findings) + 1:02d}"),
                                        "contract_id": "AUTH-01",
                                        "severity": "BLOCKER",
                                        "type": "missing_auth_annotation",
                                        "description": (
                                            f"Mutating endpoint without @PreAuthorize in {fname}"
                                        ),
                                        "evidence_type": "static_analysis",
                                        "confidence": 0.92,
                                    }
                                )

    return {"static_findings": static_findings}
