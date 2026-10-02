"""One fail-closed acceptance policy shared by jobs, reports and certificates.

References establish recorded coverage, not proof that a remote artifact still
exists. Artifact digest verification remains the responsibility of the replay
and certificate consumers. This policy performs no I/O.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

_EMPTY_REFERENCES = frozenset({"", "-", "—", "none", "null", "n/a", "unknown", "pending"})


def references(row: Mapping[str, Any], *keys: str) -> list[str]:
    """Read legacy and current evidence fields without accepting placeholders."""
    found: set[str] = set()
    for key in keys:
        raw = row.get(key)
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in values:
            if isinstance(value, str) and value.strip().lower() not in _EMPTY_REFERENCES:
                found.add(value.strip())
    return sorted(found)


def evidence_references(row: Mapping[str, Any]) -> list[str]:
    return references(row, "evidence_refs", "evidence_ref", "evidence", "evidence_digest")


@dataclass(frozen=True)
class VerificationDecision:
    status: str
    reasons: tuple[str, ...]
    passed: int
    failed: int
    unverified: int
    total: int

    @property
    def reason(self) -> str:
        return "；".join(self.reasons)


#: Every veto sentence produced by :func:`release_gate_veto` starts with this
#: prefix, and the CLI selects the gate's own reasons out of a decision by it.
#: A constant because two modules have to agree on the spelling, not on prose.
RELEASE_GATE_REASON_PREFIX = "RELEASE 档发布门"


def _gate_row(name: str, entry: Any) -> str:
    """One gate's verdict word, read from what the gate actually recorded.

    The overall ``passed`` flag is the node's own summary; a veto has to say
    *which* gate refused, so each entry is read here. An entry with no flag and
    an entry that checked nothing are both reported as 未判定 — silence is not
    agreement.
    """
    if isinstance(entry, Mapping):
        if "passed" not in entry:
            return "未判定"
        return "通过" if entry["passed"] else "未通过"
    if isinstance(entry, (list, tuple)):
        if not entry:
            return "未判定（没有条目可校验）"
        ok = all(
            isinstance(item, Mapping) and item.get("digest_ok") is True
            for item in entry
        )
        return "通过" if ok else "未通过"
    return "未判定"


def release_gate_veto(release: Mapping[str, Any] | None) -> tuple[str, tuple[str, ...]]:
    """Veto an outward ``VERIFIED`` when the RELEASE tier's own gates refuse.

    ``--depth RELEASE`` re-runs the generated test on HEAD and recomputes every
    capsule digest (``agent/nodes/run_release_checks.py``). Until #151 nothing
    listened to that result: the CLI issued a Merge Certificate, published the
    GitHub Check and persisted the job summary from contract rows alone, so the
    strongest tier the product offers certified a campaign whose evidence had
    just failed to reproduce.

    Returns ``(status, reasons)``; ``("", ())`` when the tier recorded no gate
    verdict to listen to — a FAST/DEEP job, or a caller that never ran the node.
    The status stays inside this module's existing vocabulary: a gate refusal
    blocks acceptance, it does not invent a fourth state.
    """
    payload = release if isinstance(release, Mapping) else {}
    gates = payload.get("gates")
    if not isinstance(gates, Mapping) or not gates:
        return "", ()
    if payload.get("passed") is True:
        return "", ()
    reasons = tuple(
        f"{RELEASE_GATE_REASON_PREFIX} {name}: {_gate_row(name, gates[name])}"
        for name in sorted(gates)
    )
    return "BLOCKED", reasons


def evaluate_acceptance(
    matrix: Mapping[str, Any] | None,
    *,
    contracts: Sequence[Mapping[str, Any]] | None = None,
    findings: Sequence[Any] = (),
    errors: Sequence[Any] = (),
    release: Mapping[str, Any] | None = None,
) -> VerificationDecision:
    """Contract policy plus the RELEASE tier's veto — one shared entry point.

    Callers that have no release state pass nothing and get exactly
    :func:`evaluate_verification`. A veto can only ever downgrade VERIFIED, so
    it never turns a FAILED or BLOCKED job into something reassuring.
    """
    decision = evaluate_verification(
        matrix, contracts=contracts, findings=findings, errors=errors
    )
    status, reasons = release_gate_veto(release)
    if not status or decision.status != "VERIFIED":
        return decision
    return replace(
        decision,
        status=status,
        reasons=tuple(dict.fromkeys(decision.reasons + reasons)),
    )


def evaluate_verification(
    matrix: Mapping[str, Any] | None,
    *,
    contracts: Sequence[Mapping[str, Any]] | None = None,
    findings: Sequence[Any] = (),
    errors: Sequence[Any] = (),
    require_experiment: bool = True,
) -> VerificationDecision:
    """Accept only complete, unique, evidenced PASS rows with no contradictions.

    Counters can veto contradictory records, but can never replace the rows.
    When compiled contracts are available, match their IDs, not just counts.
    Certificates reuse this policy with contract-shaped rows and do not require
    the matrix-only experiment field.
    """
    matrix = matrix if isinstance(matrix, Mapping) else {}
    raw_rows = matrix.get("rows")
    rows = raw_rows if isinstance(raw_rows, (list, tuple)) else []
    reasons: list[str] = []
    passed = failed = unverified = 0
    ids: set[str] = set()
    if not rows:
        reasons.append("零检查不能判定验收通过：请补充验收条件并接入适用检查器")
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping):
            unverified += 1
            reasons.append(f"第 {index} 条检查记录格式无效")
            continue
        cid = str(row.get("contract_id") or row.get("id") or "").strip()
        label = cid or f"第 {index} 条检查"
        duplicate = bool(cid and cid in ids)
        if not cid:
            reasons.append(f"{label}缺少契约标识")
        elif duplicate:
            reasons.append(f"契约 {cid} 存在重复检查行，需合并冲突证据")
        if cid:
            ids.add(cid)
        result = row.get("result")
        if result == "FAIL":
            failed += 1
            reasons.append(f"{label}检查失败")
        elif result != "PASS":
            unverified += 1
            reasons.append(f"{label}尚未得到可判定结果")
        else:
            has_evidence = bool(evidence_references(row))
            has_experiment = not require_experiment or bool(
                references(row, "experiment_ids", "experiment_id", "experiment")
            )
            if not has_evidence:
                reasons.append(f"{label}标记通过但缺少证据引用")
            if not has_experiment:
                reasons.append(f"{label}标记通过但缺少实验记录")
            if has_evidence and has_experiment and cid and not duplicate:
                passed += 1
            else:
                unverified += 1

    if contracts is None and isinstance(matrix.get("contract_ids"), list):
        contracts = [{"id": cid} for cid in matrix["contract_ids"]]
    if contracts is not None:
        expected: set[str] = set()
        for contract in contracts:
            cid = str(contract.get("id") or contract.get("contract_id") or "").strip()
            if not cid or cid in expected:
                reasons.append("验收契约标识缺失或重复，无法确定完整覆盖范围")
            if cid:
                expected.add(cid)
        missing = sorted(expected - ids)
        if missing:
            reasons.append("缺少契约检查结果：" + ", ".join(missing))
            unverified += len(missing)
        unexpected = sorted(ids - expected)
        if unexpected:
            reasons.append("检查记录没有对应验收契约：" + ", ".join(unexpected))
        if not expected:
            reasons.append("没有有效的验收契约，无法确认需求覆盖")

    # Compare declared counts to the original row verdicts. Effective counts
    # above additionally downgrade PASS without evidence to unverified.
    for key, expected_count in (
        ("total_rows", len(rows)),
        ("passed", sum(isinstance(r, Mapping) and r.get("result") == "PASS" for r in rows)),
        ("failed", sum(isinstance(r, Mapping) and r.get("result") == "FAIL" for r in rows)),
        ("unverified", sum(
            isinstance(r, Mapping) and r.get("result") == "UNVERIFIED" for r in rows
        )),
    ):
        if key in matrix:
            count = matrix[key]
            if type(count) is not int or count != expected_count:
                reasons.append(f"检查汇总 {key} 与实际检查记录不一致")
    if "total_contracts" in matrix:
        count = matrix["total_contracts"]
        if type(count) is not int or count <= 0 or count > len(ids):
            reasons.append("契约总数与检查覆盖不一致")
    if findings:
        reasons.append(f"存在 {len(findings)} 项已确认问题，需要处理后重新验收")
    if errors:
        reasons.append("执行过程有错误，无法形成有效验收结论")
    return VerificationDecision(
        "FAILED" if errors else "BLOCKED" if reasons else "VERIFIED",
        tuple(dict.fromkeys(reasons)), passed, failed, unverified,
        max(len(rows), passed + failed + unverified),
    )


def contracts_with_results(
    contracts: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach fail-priority results without last-write-wins certification gaps."""
    from agent.matrix_policy import merge_contract_results

    # merge_contract_results accepts list[dict]; the callers pass read-only
    # Mapping views (e.g. state entries), so materialise them here rather
    # than widening the merger's contract.
    entries = [dict(row) for row in results]
    merged = {row["contract_id"]: row for row in merge_contract_results(entries)}
    output = []
    for contract in contracts:
        row = merged.get(contract.get("id"), {})
        output.append({
            **contract,
            "result": row.get("result", "UNVERIFIED"),
            "evidence_refs": row.get("evidence_refs", []),
            "evidence_ref": next(iter(row.get("evidence_refs", [])), ""),
            "experiment_ids": row.get("experiment_ids", []),
        })
    return output
