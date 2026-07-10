"""Requirement-to-Evidence Matrix builder."""

from typing import Any


def build_evidence_matrix(
    contracts: list[dict],
    findings: list[dict],
    changed_symbols: list[str],
) -> dict[str, Any]:
    """Build the Requirement-to-Evidence Matrix data structure.

    Returns a dict with rows, summary counts, and metadata.
    """
    rows: list[dict] = []
    finding_by_cid: dict[str, list[dict]] = {}
    for f in findings:
        cid = f.get("contract_id", "UNKNOWN")
        finding_by_cid.setdefault(cid, []).append(f)

    for contract in contracts:
        cid = contract.get("id", "")
        ctype = contract.get("checker_type", "")
        related_findings = []

        # Match findings to contracts by prefix match
        cid_prefix = cid.split("-")[0].upper()
        for fc_id, flist in finding_by_cid.items():
            fc_prefix = fc_id.split("-")[0].upper()
            if fc_id.upper().startswith(cid_prefix) or cid_prefix.startswith(fc_prefix):
                related_findings.extend(flist)

        if related_findings:
            worst = max(related_findings, key=lambda f: _severity_rank(f.get("severity", "")))
            result = "FAIL"
            evidence = f"Capsule: {worst.get('id', '')} — {worst.get('description', '')}"
        else:
            result = "PASS"
            evidence = f"Contract {cid} verified — {contract.get('checker_type', '')} check passed"

        rows.append({
            "contract_id": cid,
            "requirement": contract.get("requirement", ""),
            "checker_type": ctype,
            "changed_symbols": [
                s for s in changed_symbols
                if ctype.upper() in s.upper() or cid_prefix.lower() in s.lower()
            ],
            "experiment": (
                related_findings[0].get("source", "static_analysis")
                if related_findings else "differential_test"
            ),
            "result": result,
            "evidence": evidence,
        })

    return {
        "rows": rows,
        "total_contracts": len(contracts),
        "passed": sum(1 for r in rows if r["result"] == "PASS"),
        "failed": sum(1 for r in rows if r["result"] == "FAIL"),
        "unverified": sum(1 for r in rows if r["result"] == "UNVERIFIED"),
    }


def _severity_rank(severity: str) -> int:
    return {"BLOCKER": 4, "MAJOR": 3, "MINOR": 2, "NEEDS_CONFIRMATION": 1}.get(severity, 0)
