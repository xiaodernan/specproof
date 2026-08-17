"""build_matrix node — build the Requirement-to-Evidence Matrix.

Honesty contract (v2):
- A contract row may be PASS or FAIL only when a real experiment produced
  that result (recorded in state["contract_results"] by the nodes that ran it).
- Contracts without an experiment result are UNVERIFIED — never fabricated,
  never implicitly "passed".
"""

from agent.state import Phase0State


def build_matrix_node(state: Phase0State) -> dict:
    """Build the Requirement-to-Evidence Matrix from real contract results."""
    contracts = state.get("contracts", [])
    contract_results = state.get("contract_results", [])
    confirmed_findings = state.get("confirmed_findings", [])
    changed_symbols = state.get("changed_symbols", [])

    results_by_contract: dict[str, dict] = {}
    for r in contract_results:
        cid = r.get("contract_id", "")
        if cid:
            results_by_contract[cid] = r

    matrix_rows: list[dict] = []

    for contract in contracts:
        cid = contract.get("id", "")
        res = results_by_contract.get(cid, {})
        result = res.get("result", "UNVERIFIED")
        if result not in ("PASS", "FAIL"):
            result = "UNVERIFIED"

        row = {
            "contract_id": cid,
            "requirement": contract.get("requirement", ""),
            "checker_type": contract.get("checker_type", ""),
            "changed_symbols": [],
            "experiment": res.get("experiment", "none"),
            "result": result,
            "evidence": res.get("evidence_ref", "—"),
        }

        prefix = cid.split("-")[0].upper() if cid else ""
        for sym in changed_symbols:
            if prefix and prefix in sym.upper():
                row["changed_symbols"].append(sym)

        matrix_rows.append(row)

    # Findings whose contract is not yet represented become FAIL rows.
    for f in confirmed_findings:
        fcid = f.get("contract_id", "")
        if fcid and any(r.get("contract_id") == fcid for r in matrix_rows):
            continue
        matrix_rows.append({
            "contract_id": fcid or "EXTRA",
            "requirement": f.get("description", ""),
            "checker_type": f.get("type", ""),
            "changed_symbols": [],
            "experiment": f.get("source", "unknown"),
            "result": "FAIL",
            "evidence": f.get("id", ""),
        })

    matrix = {
        "rows": matrix_rows,
        "total_contracts": len(contracts),
        "total_rows": len(matrix_rows),
        "passed": sum(1 for r in matrix_rows if r["result"] == "PASS"),
        "failed": sum(1 for r in matrix_rows if r["result"] == "FAIL"),
        "unverified": sum(1 for r in matrix_rows if r["result"] == "UNVERIFIED"),
    }

    return {"matrix": matrix}
