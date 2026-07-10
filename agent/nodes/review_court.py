"""review_court node — Prosecutor / Defender / Judge evaluation."""

from agent.state import Phase0State


def review_court_node(state: Phase0State) -> dict:
    """Evaluate candidate findings through the Review Court process.

    Phase 0 implements a simplified Review Court:
    - Prosecutor: promote static findings + diff regressions → candidates
    - Defender: check for false positives
    - Judge: apply evidence policy and set severity/confidence
    """
    static_findings = state.get("static_findings", [])
    diff_results = state.get("diff_results", [])
    candidate_findings: list[dict] = []
    confirmed_findings: list[dict] = []

    # ── Prosecutor: gather all potential issues ──
    for sf in static_findings:
        candidate_findings.append({
            **sf,
            "source": "static_analysis",
            "status": "candidate",
        })

    for dr in diff_results:
        if dr.get("verdict") in ("REGRESSION", "AMBIGUOUS"):
            candidate_findings.append({
                "id": f"COURT-{dr.get('contract_id', 'UNKNOWN')}",
                "contract_id": dr.get("contract_id", ""),
                "severity": "MAJOR",
                "type": "differential_regression",
                "description": dr.get("detail", "Differential test regression"),
                "evidence_type": "base_pass_head_fail",
                "confidence": 0.85 if dr.get("verdict") == "REGRESSION" else 0.65,
                "source": "differential",
                "status": "candidate",
                "diff_verdict": dr.get("verdict"),
            })

    # ── Defender: filter out false positives ──
    for cf in candidate_findings:
        is_false_positive = False

        # Skip if test result is NON_REPRODUCIBLE
        if cf.get("diff_verdict") == "NON_REPRODUCIBLE":
            is_false_positive = True

        if not is_false_positive:
            confirmed_findings.append({**cf, "status": "confirmed"})

    # ── Judge: apply evidence policy ──
    for f in confirmed_findings:
        # Evidence policy from spec Section 10:
        # BLOCKER: strong executable evidence, confidence >= 0.90
        # MAJOR: at least one strong evidence, confidence >= 0.82
        # MINOR: repository evidence + logic, confidence >= 0.72

        evidence_type = f.get("evidence_type", "")
        confidence = f.get("confidence", 0.0)
        is_strong = evidence_type in (
            "base_pass_head_fail",
            "static_analysis",
            "deterministic_contract_failure",
        )

        if is_strong and confidence >= 0.90:
            f["severity"] = "BLOCKER"
        elif is_strong and confidence >= 0.82:
            f["severity"] = "MAJOR"
        elif confidence >= 0.72:
            f["severity"] = "MINOR"
        else:
            f["severity"] = "NEEDS_CONFIRMATION"

    return {
        "candidate_findings": candidate_findings,
        "confirmed_findings": confirmed_findings,
    }
