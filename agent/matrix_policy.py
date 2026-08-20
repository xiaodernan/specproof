"""matrix policy — the pure contract-result merge rule for the evidence matrix.

主计划 §14.1: build_matrix 必须把契约结果合并规则写成纯函数, 并对多个节点
的竞争写入做测试. Multiple nodes write the shared contract_results channel
(LangGraph replaces list values), so the merge must not depend on which node
won the race. This module is that merge, as a pure function:

* FAIL beats PASS beats UNVERIFIED — a real failure is decisive, a real pass
  beats a gap, an unverified record only fills gaps;
* deterministic contention — the same multiset of entries in ANY order
  produces byte-identical rows (no last-write-wins tie-break, no randomness);
* no I/O, no randomness, no network — plain dicts in, plain dicts out.

Every row carries the §14.1 evidence fields: result source, experiment ids,
base/head verdicts, attribution, evidence refs, minimum evidence level, the
unverified reason and the next action, plus the review-court row fields
(severity / confidence / evidence_type / verdict / detail / status / source /
type / location / evidence_digest / finding_id). The court fields are filled
deterministically from the entries that carry them (confirmed findings in the
node wiring) and stay neutral ("", 0.0) otherwise. The merged verdict is also
exposed as "result" so legacy consumers (HTML report, worker counts, CLI
summary) keep reading one field without re-deriving the priority rule.
"""
from __future__ import annotations

import math
from typing import Any

#: Verdict priority: FAIL(3) > PASS(2) > UNVERIFIED(1); anything else ranks 0
#: and therefore never beats a real UNVERIFIED record.
_RESULT_PRIORITY: dict[str, int] = {"FAIL": 3, "PASS": 2, "UNVERIFIED": 1}

#: Evidence-level priority. "minimum evidence level" of a row is the
#: weakest level among the refs attached to it; no refs means "none".
_RUNTIME_LEVEL = "runtime"
_STATIC_LEVEL = "static"
_NONE_LEVEL = "none"
_LEVEL_PRIORITY: dict[str, int] = {_RUNTIME_LEVEL: 2, _STATIC_LEVEL: 1, _NONE_LEVEL: 0}

#: Review-court-aligned row fields (backlog #2). "verdict" carries the
#: court's diff_verdict value, "detail" the finding description and
#: "finding_id" the finding id, so every matrix row can be joined against
#: confirmed_findings without renaming.
COURT_ROW_FIELDS: tuple[str, ...] = (
    "severity",
    "confidence",
    "evidence_type",
    "verdict",
    "detail",
    "status",
    "source",
    "type",
    "location",
    "evidence_digest",
    "finding_id",
)

#: The §14.1 canonical row fields. merge_contract_results guarantees every
#: one of these keys on every returned row (plus the derived "result").
CANONICAL_FIELDS: tuple[str, ...] = (
    "contract_id",
    "contract_version",
    "requirement_summary",
    "changed_symbols",
    "experiment_ids",
    "base_result",
    "head_result",
    "attribution",
    "evidence_refs",
    "min_evidence_level",
    "unverified_reason",
    "next_action",
    *COURT_ROW_FIELDS,
)

#: Stable reason strings — asserted by tests/unit/test_matrix_policy.py.
UNVERIFIED_NO_EXPERIMENT_REASON = (
    "该契约没有任何实验产出结果 (contract_results 无记录); 禁止臆造 PASS/FAIL"
)
UNVERIFIED_INCONCLUSIVE_REASON = (
    "实验已运行但未得到可判定证据, 保持 UNVERIFIED"
)
NEXT_ACTION_FAIL = "阻断合并: 依据证据修复 Head 并重跑差分实验, 复审通过前不得合并"
NEXT_ACTION_PASS = "维持证据链可回放; 合并前复核实验覆盖范围"
NEXT_ACTION_UNVERIFIED = "补齐证据: 安排 DEEP 实验或人工审阅, 不得把 UNVERIFIED 当作通过"


#: Severity rank for the deterministic "strongest finding" pick among
#: court-carrying entries (review_court vocabulary; unknown values rank 0,
#: an empty severity ranks -1).
_SEVERITY_RANK: dict[str, int] = {
    "BLOCKER": 4,
    "MAJOR": 3,
    "MINOR": 2,
    "INFORMATIONAL": 1,
    "NONE": 0,
}


def confidence_or_zero(value: object) -> float:
    """Sanitize one confidence value: numeric values are clamped to [0, 1];
    bools, strings and non-finite floats collapse to 0.0."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        confidence = min(max(float(value), 0.0), 1.0)
        if math.isfinite(confidence):
            return confidence
    return 0.0


def _severity_rank(severity: str) -> int:
    """Rank one severity string; "" ranks below every real severity."""
    if not severity:
        return -1
    return _SEVERITY_RANK.get(severity, 0)


def _court_fields_of(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the review-court row fields one entry carries.

    Accepts both the row-level spellings (verdict / detail / finding_id) and
    the review-court names (diff_verdict / description / id) so court-shaped
    dicts merge without translation. Returns None when the entry carries no
    court metadata at all, so verdict-free metadata entries can never
    disturb the verdict / experiment / evidence merge.
    """
    severity = str(entry.get("severity") or "").strip()
    confidence = confidence_or_zero(entry.get("confidence"))
    evidence_type = str(entry.get("evidence_type") or "").strip()
    verdict = str(entry.get("verdict") or entry.get("diff_verdict") or "").strip()
    detail = str(entry.get("detail") or entry.get("description") or "").strip()
    status = str(entry.get("status") or "").strip()
    source = str(entry.get("source") or "").strip()
    entry_type = str(entry.get("type") or "").strip()
    location = str(entry.get("location") or "").strip()
    evidence_digest = str(entry.get("evidence_digest") or "").strip()
    finding_id = str(entry.get("finding_id") or entry.get("id") or "").strip()

    if not any((
        severity,
        confidence,
        evidence_type,
        verdict,
        detail,
        status,
        source,
        entry_type,
        location,
        evidence_digest,
        finding_id,
    )):
        return None
    return {
        "severity": severity,
        "confidence": confidence,
        "evidence_type": evidence_type,
        "verdict": verdict,
        "detail": detail,
        "status": status,
        "source": source,
        "type": entry_type,
        "location": location,
        "evidence_digest": evidence_digest,
        "finding_id": finding_id,
    }


def _court_sort_key(court: dict[str, Any]) -> tuple[int, float, str]:
    """Deterministic "strongest finding" order: severity rank desc, then
    confidence desc, then finding id asc — never the entry order."""
    return (
        -_severity_rank(str(court.get("severity", ""))),
        -confidence_or_zero(court.get("confidence")),
        str(court.get("finding_id", "")),
    )


def _priority(result: object) -> int:
    """Priority rank of one verdict string; unknown values rank 0."""
    if isinstance(result, str):
        return _RESULT_PRIORITY.get(result.upper(), 0)
    return 0


def _merge_verdict(results: list[str]) -> str:
    """FAIL > PASS > UNVERIFIED over the given verdicts (empty -> UNVERIFIED)."""
    best = "UNVERIFIED"
    best_rank = _RESULT_PRIORITY["UNVERIFIED"]
    for result in results:
        rank = _priority(result)
        if rank > best_rank:
            best = result.upper()
            best_rank = rank
    return best


def _evidence_level(ref: str) -> str:
    """Map one evidence ref to its level: sha256 digests are runtime
    evidence (differential execution); everything else is static."""
    if ref.startswith("sha256:"):
        return _RUNTIME_LEVEL
    return _STATIC_LEVEL


def _refs_of(entry: dict[str, Any]) -> list[str]:
    """All evidence refs one entry carries, sanitized and deduplicated."""
    refs: list[str] = []
    raw = entry.get("evidence_ref")
    if isinstance(raw, str):
        refs.append(raw)
    listed = entry.get("evidence_refs")
    if isinstance(listed, list):
        refs.extend(item for item in listed if isinstance(item, str))
    return sorted({ref.strip() for ref in refs if ref.strip() and ref.strip() != "—"})


def _experiments_of(entry: dict[str, Any]) -> list[str]:
    """All experiment ids one entry carries, sanitized and deduplicated."""
    experiments: list[str] = []
    for key in ("experiment", "experiment_id"):
        raw = entry.get(key)
        if isinstance(raw, str):
            experiments.append(raw)
    listed = entry.get("experiment_ids")
    if isinstance(listed, list):
        experiments.extend(item for item in listed if isinstance(item, str))
    return sorted(
        {
            value.strip()
            for value in experiments
            if value.strip() and value.strip() not in ("none", "—")
        }
    )


def _entry_level(entry: dict[str, Any]) -> int:
    """Strongest evidence level among the refs of one entry (0 = none)."""
    refs = _refs_of(entry)
    if not refs:
        return _LEVEL_PRIORITY[_NONE_LEVEL]
    return max(_LEVEL_PRIORITY[_evidence_level(ref)] for ref in refs)


def _entry_sort_key(entry: dict[str, Any]) -> tuple[int, str, str]:
    """Deterministic contention key: strongest evidence first, then the
    lexicographically smallest experiment/ref pair — order-independent."""
    return (
        -_entry_level(entry),
        ",".join(_experiments_of(entry)),
        ",".join(_refs_of(entry)),
    )


def _merged_attribution(group: list[dict[str, Any]], verdict: str) -> str:
    """Row attribution: PASS rows carry none, UNVERIFIED rows unknown, FAIL
    rows the attribution of the strongest-evidence attributed entry (the
    head/base/not_attributed vocabulary of the Review Court policy layer)."""
    if verdict == "PASS":
        return "none"
    if verdict == "UNVERIFIED":
        return "unknown"
    attributed: list[dict[str, Any]] = []
    for entry in group:
        raw_attribution = entry.get("attribution")
        if isinstance(raw_attribution, str) and raw_attribution.strip():
            attributed.append(entry)
    if not attributed:
        return "head"
    winner = min(attributed, key=_entry_sort_key)
    attr = winner.get("attribution")
    return attr if isinstance(attr, str) and attr.strip() else "head"


def _merge_group(contract_id: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge every entry of one contract into its canonical row."""
    verdict = _merge_verdict(
        [
            entry["result"].upper()
            for entry in group
            if isinstance(entry.get("result"), str)
        ]
    )

    versions = [
        int(entry["contract_version"])
        for entry in group
        if isinstance(entry.get("contract_version"), int)
        and not isinstance(entry.get("contract_version"), bool)
    ]
    contract_version = max(versions, default=1)

    summaries = sorted(
        {
            str(entry["requirement_summary"]).strip()
            for entry in group
            if isinstance(entry.get("requirement_summary"), str)
            and str(entry["requirement_summary"]).strip()
        }
    )
    # Deterministic pick: the longest summary (most informative), ties broken
    # lexicographically — never the entry order.
    requirement_summary = (
        sorted(summaries, key=lambda text: (-len(text), text))[0] if summaries else ""
    )

    symbols: set[str] = set()
    for entry in group:
        listed = entry.get("changed_symbols")
        if isinstance(listed, list):
            symbols.update(item for item in listed if isinstance(item, str) and item.strip())
    changed_symbols = sorted(symbols)

    experiment_ids: list[str] = []
    seen_experiments: set[str] = set()
    for entry in group:
        for experiment in _experiments_of(entry):
            if experiment not in seen_experiments:
                seen_experiments.add(experiment)
                experiment_ids.append(experiment)
    experiment_ids.sort()

    evidence_refs: list[str] = []
    seen_refs: set[str] = set()
    for entry in group:
        for ref in _refs_of(entry):
            if ref not in seen_refs:
                seen_refs.add(ref)
                evidence_refs.append(ref)
    evidence_refs.sort()

    base_result = _merge_verdict(
        [
            entry["base_result"].upper()
            for entry in group
            if isinstance(entry.get("base_result"), str)
        ]
    )
    head_result = _merge_verdict(
        [
            entry["head_result"].upper()
            for entry in group
            if isinstance(entry.get("head_result"), str)
        ]
    )

    if evidence_refs:
        min_evidence_level = min(
            evidence_refs, key=lambda ref: _LEVEL_PRIORITY[_evidence_level(ref)]
        )
        min_evidence_level = _evidence_level(min_evidence_level)
    else:
        min_evidence_level = _NONE_LEVEL

    if verdict == "UNVERIFIED":
        unverified_reason = (
            UNVERIFIED_INCONCLUSIVE_REASON if experiment_ids else UNVERIFIED_NO_EXPERIMENT_REASON
        )
        next_action = NEXT_ACTION_UNVERIFIED
    elif verdict == "FAIL":
        unverified_reason = ""
        next_action = NEXT_ACTION_FAIL
    else:
        unverified_reason = ""
        next_action = NEXT_ACTION_PASS

    # ── Review-court row fields (backlog #2) ────────────────────
    # Filled from the entries that carry court metadata (confirmed
    # findings in the node wiring); the deterministic winner is the
    # strongest severity / confidence / finding-id entry. Court metadata
    # never participates in the verdict / experiment / evidence merge.
    court_candidates: list[dict[str, Any]] = []
    for entry in group:
        court = _court_fields_of(entry)
        if court is not None:
            court_candidates.append(court)
    if court_candidates:
        court_fields = min(court_candidates, key=_court_sort_key)
    else:
        court_fields = dict.fromkeys(COURT_ROW_FIELDS, "")
        court_fields["confidence"] = 0.0

    row: dict[str, Any] = {
        "contract_id": contract_id,
        "contract_version": contract_version,
        "requirement_summary": requirement_summary,
        "changed_symbols": changed_symbols,
        "experiment_ids": experiment_ids,
        "base_result": base_result,
        "head_result": head_result,
        "attribution": _merged_attribution(group, verdict),
        "evidence_refs": evidence_refs,
        "min_evidence_level": min_evidence_level,
        "unverified_reason": unverified_reason,
        "next_action": next_action,
        # Legacy consumers (HTML report, worker counts, CLI summary) read
        # one merged verdict field; keep it derived from the same priority
        # rule so counts and rows can never disagree.
        "result": verdict,
        **court_fields,
    }
    return row


def merge_contract_results(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge per-contract evidence entries into canonical matrix rows.

    Pure and deterministic: groups entries by contract_id, applies the
    FAIL > PASS > UNVERIFIED priority (order-independently) and returns one
    row per contract sorted by contract_id. Entries without a non-empty
    string contract_id are ignored. Every row carries CANONICAL_FIELDS plus
    the derived "result".
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_id = entry.get("contract_id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        groups.setdefault(raw_id.strip(), []).append(entry)

    return [_merge_group(contract_id, group) for contract_id, group in sorted(groups.items())]
