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

Backlog #2: every row now also carries the complete review-court field set
(severity / confidence / evidence_type / verdict / detail / status / source /
type / location / evidence_digest / finding_id — COMPLETE_ROW_FIELDS).
Confirmed findings feed those fields for known and unknown contracts alike;
for a known contract the court metadata is attached WITHOUT a result, so it
can never fabricate or downgrade a verdict (verdicts still come only from
real experiment results). The build is a pure function of the state dict:
no clock, no randomness, no module-level mutable state.

Counters (#199): ``build_matrix_runs_total`` counts every invocation and
``build_matrix_outcomes_<word>_total`` records how the build ended —
``no_contracts`` (the state carried an empty contract list: the matrix is
assembled from findings alone), ``pass_downgraded`` (at least one PASS row
was refused by this node's own evaluate_verification gate and rewritten to
UNVERIFIED — the matrix declining to back a verdict) or ``built`` (a
normal build). The row counts alone cannot separate a contract-less
matrix from a fully-UNVERIFIED one; the word separates the empty-contract
jobs and the refusal events.
"""
from typing import Any

from agent.external_observation import (
    observation_limits,
    observation_status,
    observations,
)
from agent.matrix_policy import (
    CANONICAL_FIELDS,
    NEXT_ACTION_UNVERIFIED,
    confidence_or_zero,
    merge_contract_results,
)
from agent.state import Phase0State
from evidence.verdict import (
    ROW_REASON_CONTRACT_NOT_APPROVED,
    evaluate_verification,
)
from observability.metrics import incr

#: Why a row for a never-approved contract is UNVERIFIED. The reader's
#: next action is to APPROVE the contract, not to go looking for missing
#: evidence — and a bare "UNVERIFIED" does not say which.
UNAPPROVED_CONTRACT_REASON = "契约未获批准：需人工批准后方可作为验收依据"

#: diff_results verdict -> row attribution (Review Court vocabulary).
_ATTRIBUTION_BY_VERDICT: dict[str, str] = {
    "REGRESSION": "head",
    "UNEXPECTED_FIX": "base",
    "AMBIGUOUS": "not_attributed",
    "COMPLIANT": "none",
}

#: Row keys the HTML report and the worker/CLI counts have always read.
LEGACY_ROW_FIELDS: tuple[str, ...] = (
    "requirement",
    "checker_type",
    "experiment",
    "evidence",
)

#: The row fields that carry what the EXTERNAL observation could not say
#: (#365). The row's verdict still comes only from a real experiment;
#: these two fields say how far the outside-of-the-JVM observation can
#: vouch for that verdict. ``observation_status`` is the observation's
#: own status word ("" when there was no observation at all) and
#: ``observation_limits`` are the disclosed limits (empty when the
#: observation had none). Both are always present: "blank, not missing".
OBSERVATION_ROW_FIELDS: tuple[str, ...] = (
    "observation_status",
    "observation_limits",
)

#: The complete matrix row field set (backlog #2): the canonical §14.1
#: fields (including the review-court row fields) + the derived "result" +
#: the legacy renderer keys + the external-observation disclosure. Every
#: row returned by build_matrix_node carries all of these.
COMPLETE_ROW_FIELDS: tuple[str, ...] = (
    *CANONICAL_FIELDS,
    "result",
    *LEGACY_ROW_FIELDS,
    *OBSERVATION_ROW_FIELDS,
)

#: The closed set of ways a matrix build can end (#199). Mirrored by the
#: parity family's regex and the behavior tests — a new word must move all
#: three together.
BUILD_MATRIX_OUTCOMES = frozenset({
    "built",            # normal build — contracts present, verdicts stand
    "no_contracts",     # empty contract list — findings-only matrix
    "pass_downgraded",  # >=1 PASS row refused by the node's own gate
})


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


def _court_fields_of_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Map one confirmed finding onto the review-court row fields.

    Names follow the matrix row contract (backlog #2): "verdict" is the
    court's diff_verdict value, "detail" the finding description and
    "finding_id" the finding id. Missing values stay neutral ("", 0.0).

    #261/#262: the in-flight evidence run_differential captures
    (behavioral_evidence / db_violation_evidence / db_state_detail) rides
    along verbatim so the matrix row — and every downstream projection that
    reads it — can explain *why* a (possibly scaffold-wiped) verdict was
    reached. The evidence fields are structured dicts, so they are carried
    as-is (never stringified); missing evidence stays a neutral empty dict.
    """
    return {
        "severity": str(finding.get("severity") or "").strip(),
        "confidence": confidence_or_zero(finding.get("confidence")),
        "evidence_type": str(finding.get("evidence_type") or "").strip(),
        "verdict": str(finding.get("diff_verdict") or "").strip(),
        "detail": str(finding.get("description") or "").strip(),
        "status": str(finding.get("status") or "").strip(),
        "source": str(finding.get("source") or "").strip(),
        "type": str(finding.get("type") or "").strip(),
        "location": str(finding.get("location") or "").strip(),
        "evidence_digest": str(finding.get("evidence_digest") or "").strip(),
        "finding_id": str(finding.get("id") or "").strip(),
        "db_state_detail": str(finding.get("db_state_detail") or "").strip(),
        "db_violation_evidence": _evidence_dict(finding.get("db_violation_evidence")),
        "behavioral_evidence": _evidence_dict(finding.get("behavioral_evidence")),
    }


def _evidence_dict(value: Any) -> dict[str, Any]:
    """Coerce a captured evidence field to a JSON-safe dict (else {}).

    The in-flight evidence run_differential emits (#250/#253/#254) is a
    structured dict; carrying it through the string-bound projections means it
    must never be stringified or dropped. Anything that is not already a dict
    (None, a stale string, garbage) becomes an empty dict so a row is never
    poisoned by one malformed field.
    """
    return dict(value) if isinstance(value, dict) else {}


def build_matrix_node(state: Phase0State) -> dict[str, Any]:
    """Build the Requirement-to-Evidence Matrix from real contract results."""
    incr("build_matrix_runs_total")
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
        result_entry = {
            "contract_id": cid,
            "result": result.get("result", "UNVERIFIED"),
            "experiment": result.get("experiment", ""),
            "evidence_ref": result.get("evidence_ref", ""),
        }
        # P3-6: the reason a contract is UNVERIFIED rides along. Without it
        # the row says only "no result" and the reader cannot tell "the
        # experiment never ran" from "the experiment ran and found nothing".
        details = str(result.get("details") or "").strip()
        if details:
            result_entry["details"] = details
        entries.append(result_entry)

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
        # WHERE the differential actually ran (docker_sandbox /
        # local_host_no_sandbox / unconfirmed). This is a safety disclosure,
        # not decoration: a host-surface run executes the untrusted PR's own
        # tests on the operator's machine, and the reader is entitled to know
        # which of the two happened. Dropped here it never reaches any UI.
        surface = str(diff.get("execution_surface") or "").strip()
        if surface:
            entry["execution_surface"] = surface
        # Where the workspace's dependencies came from (offline install from
        # the seeded cache / skipped / host flow) — the provenance sibling of
        # execution_surface, disclosed for the same reason.
        install = str(diff.get("dependency_install") or "").strip()
        if install:
            entry["dependency_install"] = install
        digest = diff.get("evidence_digest", "")
        if digest:
            entry["evidence_ref"] = digest
        entries.append(entry)

    # Findings whose contract has no compiled contract become FAIL rows
    # (one row per contract after the merge; legacy shape kept for EXTRA).
    # Every finding — known and unknown contracts alike — contributes its
    # review-court row fields. For a known contract the court metadata
    # rides along WITHOUT a result, so it can never fabricate or downgrade
    # a verdict: the row verdict still comes only from real experiments.
    for finding in confirmed_findings:
        fcid = finding.get("contract_id", "")
        court_fields = _court_fields_of_finding(finding)
        if fcid and fcid in known_ids:
            entries.append({"contract_id": fcid, **court_fields})
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
            **court_fields,
        })

    # ── Pure merge (§14.1) ────────────────────────────────────────────
    rows = merge_contract_results(entries)

    # ── Legacy row shape for existing consumers ───────────────────────
    matrix_rows: list[dict[str, Any]] = []
    pass_downgraded = False
    # What the outside of the JVM actually showed for each contract
    # (#365). The comparison lives in ONE place (agent.external_observation)
    # — the same builder the evidence pack files — so the row and the
    # pack cannot disagree about what was observed. A failure to observe
    # is never fatal to the matrix: the matrix is the verdict layer, and
    # an unreadable observation must not become a verdict.
    contract_observations: dict[str, Any] = {}
    try:
        contract_observations = observations(state)
    except Exception:  # noqa: BLE001 — degraded, not fatal
        contract_observations = {}
    # A contract that was never approved cannot back an acceptance — the
    # Review Court's condition 1 refuses to certify on it. The row must
    # SAY so: a bare "UNVERIFIED" sends the reader after missing
    # evidence, while the next action is "approve the contract".
    unapproved = {
        str(c.get("id") or "")
        for c in contracts
        if c.get("approved") is False
    }
    for row in rows:
        legacy = dict(row)
        legacy["requirement"] = row["requirement_summary"]
        legacy["checker_type"] = checker_types.get(row["contract_id"], "")
        legacy["experiment"] = row["experiment_ids"][0] if row["experiment_ids"] else "none"
        legacy["evidence"] = row["evidence_refs"][0] if row["evidence_refs"] else "—"
        # What the external observation could and could not say about this
        # contract. A reader who sees PASS must be able to tell whether
        # the outside of the JVM was actually compared — and where that
        # comparison stopped. The verdict itself is untouched: these two
        # fields disclose, they do not decide.
        observation = contract_observations.get(str(row.get("contract_id") or ""))
        legacy["observation_status"] = observation_status(observation)
        legacy["observation_limits"] = observation_limits(observation)
        if legacy["result"] == "PASS":
            decision = evaluate_verification({"rows": [legacy]})
            if decision.status != "VERIFIED":
                legacy["result"] = "UNVERIFIED"
                legacy["unverified_reason"] = decision.reason
                legacy["next_action"] = NEXT_ACTION_UNVERIFIED
                pass_downgraded = True
        elif legacy["result"] == "UNVERIFIED" and legacy["contract_id"] in unapproved:
            legacy["unverified_reason"] = UNAPPROVED_CONTRACT_REASON
            legacy["unverified_reason_code"] = ROW_REASON_CONTRACT_NOT_APPROVED
            legacy["next_action"] = NEXT_ACTION_UNVERIFIED
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
        "contract_ids": [contract.get("id", "") for contract in contracts],
        "total_rows": len(matrix_rows),
        "passed": sum(1 for row in matrix_rows if row["result"] == "PASS"),
        "failed": sum(1 for row in matrix_rows if row["result"] == "FAIL"),
        "unverified": sum(1 for row in matrix_rows if row["result"] == "UNVERIFIED"),
    }

    if not contracts:
        incr("build_matrix_outcomes_no_contracts_total")
    elif pass_downgraded:
        incr("build_matrix_outcomes_pass_downgraded_total")
    else:
        incr("build_matrix_outcomes_built_total")

    return {"matrix": matrix}
