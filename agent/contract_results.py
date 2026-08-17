
"""Shared per-contract experiment-result merge for SpecProof pipeline nodes.

LangGraph merges node return dicts channel by channel: a list value returned
by a later node REPLACES the earlier one. Without an explicit merge, the
differential node wiped the static-check results (and vice versa), turning
real PASS/FAIL rows into UNVERIFIED at the matrix stage.

Every node that produces contract_results must merge through this function.
"""
from typing import Any


def merge_contract_results(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge per-contract results with FAIL-priority semantics.

    - keyed by contract_id
    - FAIL beats PASS and UNVERIFIED (a real failure is decisive)
    - PASS beats UNVERIFIED
    - UNVERIFIED fills gaps only
    """
    merged: dict[str, dict[str, Any]] = {}
    for r in existing:
        cid = r.get("contract_id", "")
        if cid:
            merged[cid] = dict(r)
    for r in incoming:
        cid = r.get("contract_id", "")
        if not cid:
            continue
        old = merged.get(cid)
        if old is None:
            merged[cid] = dict(r)
            continue
        rank = {"FAIL": 3, "PASS": 2, "UNVERIFIED": 1}
        # >= (not >): on a tie the LATER experiment wins — it usually carries
        # the stronger evidence (e.g. differential sha256 digest vs static
        # finding id).
        if rank.get(r.get("result", ""), 0) >= rank.get(old.get("result", ""), 0):
            merged[cid] = dict(r)
    return list(merged.values())
