"""build_matrix node — build the Requirement-to-Evidence Matrix."""

from agent.state import Phase0State


def build_matrix_node(state: Phase0State) -> dict:
    """Build the Requirement-to-Evidence Matrix from contracts and findings."""
    contracts = state.get("contracts", [])
    confirmed_findings = state.get("confirmed_findings", [])

    matrix_rows: list[dict] = []

    for contract in contracts:
        cid = contract.get("id", "")
        cid_prefix = cid.split("-")[0].upper()
        finding = None
        for f in confirmed_findings:
            fid = f.get("contract_id", "")
            # Match by direct prefix, or by finding ID containing contract prefix
            if fid and (fid.upper().startswith(cid_prefix) or cid_prefix in fid.upper()):
                finding = f
                break

        row = {
            "contract_id": cid,
            "requirement": contract.get("requirement", ""),
            "checker_type": contract.get("checker_type", ""),
            "changed_symbols": [],
            "experiment": "static_analysis" if finding else "differential_test",
            "result": "FAIL" if finding else "PASS",
            "evidence": finding.get("id", "") if finding else "Run OK",
        }

        # Link changed symbols
        for sym in state.get("changed_symbols", []):
            if cid.split("-")[0].upper() in sym.upper():
                row["changed_symbols"].append(sym)

        matrix_rows.append(row)

    # Add any extra findings not linked to contracts
    for f in confirmed_findings:
        if not any(r.get("evidence", "") == f.get("id", "") for r in matrix_rows):
            matrix_rows.append(
                {
                    "contract_id": f.get("contract_id", "EXTRA"),
                    "requirement": f.get("description", ""),
                    "checker_type": f.get("type", ""),
                    "changed_symbols": [],
                    "experiment": f.get("source", "unknown"),
                    "result": "FAIL",
                    "evidence": f.get("id", ""),
                }
            )

    matrix = {
        "rows": matrix_rows,
        "total_contracts": len(contracts),
        "total_rows": len(matrix_rows),
        "passed": sum(1 for r in matrix_rows if r["result"] == "PASS"),
        "failed": sum(1 for r in matrix_rows if r["result"] == "FAIL"),
        "unverified": sum(1 for r in matrix_rows if r["result"] == "UNVERIFIED"),
    }

    return {"matrix": matrix}
