"""run_static_checks node — deterministic regex checks on changed code.

P0.5 Evidence Policy:
- Static regex findings are capped at severity MAJOR (never BLOCKER).
- evidence_type is explicitly "static_regex_analysis" to distinguish from
  executable evidence (base_pass_head_fail, db_state_mutation).
- Only executable differential evidence + DB state verification can produce
  BLOCKER findings with confidence >= 0.90.
"""

import os
import re
from pathlib import Path

from agent.state import Phase0State

# P0.5: Static analysis confidence ceiling — regex alone cannot prove
# a real runtime regression, so confidence never exceeds 0.85.
_STATIC_CONFIDENCE_CEILING = 0.85


def run_static_checks_node(state: Phase0State) -> dict:
    """Run static regex-based analysis on the head workspace.

    P0.5: All static findings are capped at MAJOR severity.
    evidence_type is "static_regex_analysis" — cannot produce BLOCKER.
    """
    changed_symbols = state.get("changed_symbols", [])
    head_workspace = state.get("head_workspace", "")
    static_findings: list[dict] = []

    # Check 1: Detect @PreAuthorize removal → MAJOR (not BLOCKER)
    auth_removed = any(
        "@PreAuthorize" in sym or "PreAuthorize" in sym
        for sym in changed_symbols
        if "REMOVED" in sym or "ANNOTATION_REMOVED" in sym
    )
    if auth_removed:
        static_findings.append({
            "id": "STATIC-AUTH-01",
            "contract_id": "AUTH-01",
            "severity": "MAJOR",  # P0.5: capped at MAJOR for static regex
            "type": "annotation_removed",
            "description": "@PreAuthorize removed from controller method — "
                           "requires differential execution to confirm regression",
            "evidence_type": "static_regex_analysis",
            "confidence": min(0.85, _STATIC_CONFIDENCE_CEILING),
            "p0_5_note": "Static regex alone cannot produce BLOCKER. "
                         "Requires base_pass_head_fail + db_state_mutation evidence.",
        })

    # Check 2: Detect @Transactional removal → MINOR
    tx_removed = any(
        "@Transactional" in sym
        for sym in changed_symbols
        if "ANNOTATION_REMOVED" in sym
    )
    if tx_removed:
        static_findings.append({
            "id": "STATIC-TX-01",
            "contract_id": "TRANSACTION-01",
            "severity": "MINOR",
            "type": "annotation_removed",
            "description": "@Transactional removed — potential data inconsistency",
            "evidence_type": "static_regex_analysis",
            "confidence": 0.80,
            "p0_5_note": "Static regex alone cannot produce BLOCKER.",
        })

    # Check 3: Scan head workspace controller for missing security annotations
    if head_workspace:
        for root, _dirs, files in os.walk(head_workspace):
            for fname in files:
                if not fname.endswith("Controller.java") or "test" in root.lower():
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = Path(fpath).read_text(encoding="utf-8")
                except Exception:
                    continue

                # Find @PutMapping/@PostMapping/@DeleteMapping without @PreAuthorize
                mutating = re.findall(
                    r'(@PutMapping|@PostMapping|@DeleteMapping)\([^)]*\)\s*\n\s*public',
                    content,
                )
                if mutating:
                    for m in mutating:
                        idx = content.find(m)
                        snippet = content[max(0, idx - 80):idx]
                        if "@PreAuthorize" not in snippet and "@Secured" not in snippet:
                            static_findings.append({
                                "id": f"STATIC-MUT-{len(static_findings) + 1:02d}",
                                "contract_id": "AUTH-01",
                                "severity": "MAJOR",  # P0.5: capped at MAJOR
                                "type": "missing_auth_annotation",
                                "description": (
                                    f"Mutating endpoint without @PreAuthorize "
                                    f"in {fname}"
                                ),
                                "evidence_type": "static_regex_analysis",
                                "confidence": 0.82,
                                "p0_5_note": (
                                    "Static regex alone cannot produce BLOCKER. "
                                    "Requires differential execution evidence."
                                ),
                            })

    return {"static_findings": static_findings}
