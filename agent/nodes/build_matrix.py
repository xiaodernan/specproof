"""build_matrix node — build the Requirement-to-Evidence Matrix.

Honesty contract (v2):
- A contract row may be PASS or FAIL only when a real experiment produced
  that result (recorded in state["contract_results"] by the nodes that ran it).
- Contracts without an experiment result are UNVERIFIED — never fabricated,
  never implicitly "passed".

主计划 §14.1: the merge rule itself lives in agent.matrix_policy
(merge_contract_results) — a pure, order-independent FAIL > PASS > UNVERIFIED
merge that also fills the §14.1 row fields (experiment ids, base/head
verdicts, attribution, evidence refs, minimum evidence level, unverified
reason, next action). This node only adapts state channels into policy
entries and re-attaches the legacy row keys (requirement / checker_type /
experiment / evidence) that existing consumers render, so the matrix shape
seen by the HTML report, the worker summary and the CLI stays compatible.
"""
from typing import Any

from agent.matrix_policy import merge_contract_results
from agent.state import Phase0State

#: diff_results verdict -> row attribution (Review Court vocabulary).
_ATTRIBUTION_BY_VERDICT: dict[str, str] = {
    "REGRESSION": "head",
    "UNEXPECTED_FIX": "base",
    "AMBIGUOUS": "not_attributed",
    "COMPLIANT": "none",
}


def _exit_verdict(value: object) -> str | None:
    """Map one exit code to a per-side verdict (None = no observation)."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, str)):
        return None
    try:
        code = int(value)
    except ValueError:
        return None
    return "PASS" if code == 0 else "FAIL"


def build_matrix_node(state: Phase0State) -> dict[str, Any]:
    """Build the Requirement-to-Evidence Matrix from real contract results."""
    contracts = state.get("contracts", [])
    contract_results = state.get("contract_results", [])
    diff_results = state.get("diff_results", [])
    confirmed_findings = state.get("confirmed_findings", [])
    changed_symbols = state.get("changed_symbols", [])

    # ── Channel -> policy entries ─────────────────────────────────────
    known_ids: set[str] = set()
    entries: list[dict[str, Any]] = []
    checker_types: dict[str, str] = {}

    for contract in contracts:
        cid = contract.get("id", "")
        if not cid:
            continue
        known_ids.add(cid)
        checker_types[cid] = str(contract.get("checker_type", ""))
        prefix = cid.split("-")[0].upper() if cid else ""
        entries.append({
            "contract_id": cid,
            "contract_version": contract.get("version", 1),
            "requirement_summary": contract.get("requirement", ""),
            "changed_symbols": [
                symbol
                for symbol in changed_symbols
                if prefix and prefix in symbol.upper()
            ],
        })

    for result in contract_results:
        cid = result.get("contract_id", "")
        if not cid or cid not in known_ids:
            # Wire-compat: results for contracts the pipeline never compiled
            # never entered the matrix before and still do not.
            continue
        entries.append({
            "contract_id": cid,
            "result": result.get("result", "UNVERIFIED"),
            "experiment": result.get("experiment", ""),
            "evidence_ref": result.get("evidence_ref", ""),
        })

    for diff in diff_results:
        cid = diff.get("contract_id", "")
        if not cid or cid not in known_ids:
            continue
        entry: dict[str, Any] = {
            "contract_id": cid,
            "experiment": diff.get("experiment_id") or "DIFF-01",
            "attribution": _ATTRIBUTION_BY_VERDICT.get(
                diff.get("verdict", ""), "unknown"
            ),
        }
        base_verdict = _exit_verdict(diff.get("base_exit_code"))
        head_verdict = _exit_verdict(diff.get("head_exit_code"))
        if base_verdict is not None:
            entry["base_result"] = base_verdict
        if head_verdict is not None:
            entry["head_result"] = head_verdict
        digest = diff.get("evidence_digest", "")
        if digest:
            entry["evidence_ref"] = digest
        entries.append(entry)

    # Findings whose contract has no compiled contract become FAIL rows
    # (one row per contract after the merge; legacy shape kept for EXTRA).
    for finding in confirmed_findings:
        fcid = finding.get("contract_id", "")
        if fcid and fcid in known_ids:
            continue
        cid = fcid or "EXTRA"
        if cid not in checker_types:
            checker_types[cid] = str(finding.get("type", ""))
        entries.append({
            "contract_id": cid,
            "requirement_summary": finding.get("description", ""),
            "result": "FAIL",
            "experiment": finding.get("source", "unknown"),
            "evidence_ref": finding.get("id", ""),
            "attribution": (
                "not_attributed"
                if finding.get("severity") == "INFORMATIONAL"
                or finding.get("status") == "not_attributed"
                else "head"
            ),
        })

    # ── Pure merge (§14.1) ────────────────────────────────────────────
    rows = merge_contract_results(entries)

    # ── Legacy row shape for existing consumers ───────────────────────
    matrix_rows: list[dict[str, Any]] = []
    for row in rows:
        legacy = dict(row)
        legacy["requirement"] = row["requirement_summary"]
        legacy["checker_type"] = checker_types.get(row["contract_id"], "")
        legacy["experiment"] = row["experiment_ids"][0] if row["experiment_ids"] else "none"
        legacy["evidence"] = row["evidence_refs"][0] if row["evidence_refs"] else "—"
        matrix_rows.append(legacy)

    # Preserve the pre-policy row order: compiled contracts in order, then
    # the finding-only rows sorted by contract id.
    contract_order: dict[str, int] = {}
    for index, contract in enumerate(contracts):
        cid = contract.get("id", "")
        if cid and cid not in contract_order:
            contract_order[cid] = index
    matrix_rows.sort(
        key=lambda row: (
            contract_order.get(row["contract_id"], len(contract_order)),
            row["contract_id"],
        )
    )

    matrix = {
        "rows": matrix_rows,
        "total_contracts": len(contracts),
        "total_rows": len(matrix_rows),
        "passed": sum(1 for row in matrix_rows if row["result"] == "PASS"),
        "failed": sum(1 for row in matrix_rows if row["result"] == "FAIL"),
        "unverified": sum(1 for row in matrix_rows if row["result"] == "UNVERIFIED"),
    }

    return {"matrix": matrix}
