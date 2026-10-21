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


#: The verdict vocabulary, in one place. Four words, and the difference
#: between the two middle ones is the point:
#:
#: VERIFIED       every contract passed with evidence
#: BLOCKED        something IS wrong — a contract FAILED, or a finding
#:                was confirmed. The change is bad; fix it and re-verify.
#: NEEDS_REVIEW   nothing is proven wrong, but the evidence is insufficient
#:                — a contract with no decidable result, a missing
#:                experiment, an incomplete coverage range. A human has
#:                to judge. (It used to be BLOCKED, which sent the
#:                reader after a bug that may not exist.)
#: FAILED         the run recorded errors — no conclusion was reached.
#:
#: Both BLOCKED and NEEDS_REVIEW are fail-closed: neither accepts the
#: change. They differ in WHO has to act.
VERDICT_VERIFIED = "VERIFIED"
VERDICT_BLOCKED = "BLOCKED"
VERDICT_NEEDS_REVIEW = "NEEDS_REVIEW"
VERDICT_FAILED = "FAILED"

#: Every word the acceptance policy can produce.
VERDICT_VOCABULARY: frozenset[str] = frozenset({
    VERDICT_VERIFIED, VERDICT_BLOCKED, VERDICT_NEEDS_REVIEW, VERDICT_FAILED,
})


def _status_for(
    *, errors: Sequence[Any], blocking: Sequence[str], reasons: Sequence[str],
) -> str:
    """The verdict word for this set of reasons.

    - errors → FAILED: the run could not reach a conclusion at all;
    - a blocking reason → BLOCKED: a real problem exists;
    - only gaps → NEEDS_REVIEW: nothing is proven wrong and nothing is
      proven right, so a human has to judge;
    - no reasons → VERIFIED.
    """
    if errors:
        return VERDICT_FAILED
    if blocking:
        return VERDICT_BLOCKED
    if reasons:
        return VERDICT_NEEDS_REVIEW
    return VERDICT_VERIFIED


@dataclass(frozen=True)
class VerificationDecision:
    status: str
    reasons: tuple[str, ...]
    passed: int
    failed: int
    unverified: int
    total: int
    #: The reasons that mean "a real problem exists" — a contract that
    #: FAILED, or a confirmed finding — as opposed to the reasons that
    #: mean "the evidence is insufficient" (a contract with no decidable
    #: result, a missing experiment, an incomplete coverage range).
    #:
    #: The split is what lets the verdict say NEEDS_REVIEW instead of
    #: BLOCKED when nothing is proven wrong: both are fail-closed, but
    #: they call for different people to act. A consumer that only knows
    #: the status cannot tell them apart; this field can.
    blocking: tuple[str, ...] = ()

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

    Refusal is read from two places, because they can disagree (#152): the tier's
    own summary flag, and the per-gate rows. A row that could not be judged — no
    flag, or a roster with nothing in it — refuses just like a row that refused:
    an unchecked gate may block an acceptance, it may never support one. The
    returns stay ``(status, reasons)``, and ``("", ())`` means there was no gate
    verdict to listen to at all (a FAST/DEEP job, or a caller that never ran the
    node).

    The two refusals are told apart, because they call for different people to
    act: a gate that **refused** (``未通过``) is a real problem → BLOCKED; a
    gate that **could not be judged** (``未判定``) is an evidence gap →
    NEEDS_REVIEW. A refusal wins when both kinds are present.
    """
    payload = release if isinstance(release, Mapping) else {}
    gates = payload.get("gates")
    if not isinstance(gates, Mapping) or not gates:
        return "", ()
    words = {name: _gate_row(name, gates[name]) for name in sorted(gates)}
    refused = payload.get("passed") is not True or any(
        word != "通过" for word in words.values()
    )
    if not refused:
        return "", ()
    reasons = tuple(
        f"{RELEASE_GATE_REASON_PREFIX} {name}: {words[name]}" for name in words
    )
    if all(word == "通过" for word in words.values()):
        # Every row agrees while the tier's own summary refuses: say which of the
        # two refused, instead of handing the reader "all gates passed, therefore
        # blocked".
        reasons += (
            f"{RELEASE_GATE_REASON_PREFIX} 总判定: 未通过（节点汇总旗标拒绝）",
        )
        return VERDICT_BLOCKED, reasons
    if any(word.startswith("未通过") for word in words.values()):
        return VERDICT_BLOCKED, reasons
    # Every non-passing row is 未判定: the gate could not be judged. That is an
    # evidence gap, not a refusal — a human has to look, rather than go hunting
    # for a bug that may not exist.
    return VERDICT_NEEDS_REVIEW, reasons


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
        # A gate that REFUSED is a real problem, so its reasons are the
        # blocking ones; a gate that could not be judged is an evidence
        # gap, so its reasons are not. The decision says which — a consumer
        # must not have to re-parse the prose to know.
        blocking=(
            reasons if status == VERDICT_BLOCKED else decision.blocking
        ),
    )


#: The two kinds of reason, and what each one MEANS for the verdict.
#:
#: REASON_BLOCKING — the run produced something self-contradictory, or it
#:   found a defect. The answer is "fix the change (or the evidence) and
#:   re-verify": a contract that FAILED, a confirmed finding, a malformed
#:   row, two rows for one contract that disagree, a row for a contract
#:   that does not exist, a summary that disagrees with its own rows.
#:
#: REASON_GAP — the run could not OBTAIN, ATTRIBUTE or DECIDE the
#:   evidence. Nothing is proven wrong, and nothing is proven right. The
#:   answer is "a human has to look": no checks at all, a row with no
#:   contract id, a contract with no decidable result, a PASS with no
#:   evidence or no experiment behind it, a contract with no row, no valid
#:   contracts to check.
#:
#: Both are fail-closed — neither accepts the change. The line between
#: them is the difference between "there is something to fix" and "we
#: could not decide", and it is a TABLE rather than a boolean because
#: every reason has to pick a side knowingly: a reader told BLOCKED
#: goes looking for a defect, and one told NEEDS_REVIEW goes looking for
#: the missing evidence.
REASON_BLOCKING = "blocking"
REASON_GAP = "gap"

#: EVERY reason the acceptance policy can produce, with the text it is
#: spelled with and the side of the table it sits on.
#:
#: The table is the authority for BOTH halves: a production site names
#: the reason and the table says what it means. Before this, the kind was
#: decided at each call site, so "which reasons are blocking" could only
#: be answered by reading the code — and the answer was spread over
#: fifteen branches. Now it is one readable list, and the kind is stated
#: exactly once per reason.
#:
#: The templates use ``str.format`` fields; a site passes them by name.
REASON_TABLE: dict[str, tuple[str, str]] = {
    # key: (text template, kind)
    "zero_checks": (
        "零检查不能判定验收通过：请补充验收条件并接入适用检查器", REASON_GAP,
    ),
    "row_malformed": ("第 {index} 条检查记录格式无效", REASON_BLOCKING),
    "row_without_contract_id": ("{label}缺少契约标识", REASON_GAP),
    "duplicate_rows": (
        "契约 {cid} 存在重复检查行，需合并冲突证据", REASON_BLOCKING,
    ),
    "contract_failed": ("{label}检查失败", REASON_BLOCKING),
    "row_unverifiable": ("{label}：{text}", REASON_GAP),
    "pass_without_evidence": ("{label}标记通过但缺少证据引用", REASON_GAP),
    "pass_without_experiment": ("{label}标记通过但缺少实验记录", REASON_GAP),
    "external_observation_missing": (
        "{label}的外部观测面未被观测（存储不可达或两个时刻不可比），"
        "此通过不能作为验收依据",
        REASON_GAP,
    ),
    "contract_set_broken": (
        "验收契约标识缺失或重复，无法确定完整覆盖范围", REASON_BLOCKING,
    ),
    "missing_contract_result": (
        "缺少契约检查结果：{ids}", REASON_GAP,
    ),
    "row_without_contract": (
        "检查记录没有对应验收契约：{ids}", REASON_BLOCKING,
    ),
    "no_valid_contract": (
        "没有有效的验收契约，无法确认需求覆盖", REASON_GAP,
    ),
    "summary_mismatch": (
        "检查汇总 {key} 与实际检查记录不一致", REASON_BLOCKING,
    ),
    "contract_total_mismatch": (
        "契约总数与检查覆盖不一致", REASON_BLOCKING,
    ),
    "findings_present": (
        "存在 {count} 项已确认问题，需要处理后重新验收", REASON_BLOCKING,
    ),
    "pipeline_errors": (
        "执行过程有错误，无法形成有效验收结论", REASON_GAP,
    ),
}


def reason_text(reason_key: str, /, **fields: Any) -> tuple[str, str]:
    """The (text, kind) of a declared reason.

    The only way a reason enters the policy: a reason that is not in the
    table cannot be produced, and a table entry nobody uses is a dead
    word (the gate says so).

    The reason key is positional-only, so a reason whose text has a
    ``{key}`` field (the summary's counter name) can still be spelled.
    """
    try:
        template, kind = REASON_TABLE[reason_key]
    except KeyError:
        raise KeyError(
            f"{reason_key!r} is not a declared reason — add it to "
            "REASON_TABLE with the side of the table it belongs to"
        ) from None
    return template.format(**fields), kind

#: The controlled reasons a matrix row may carry, and the outward
#: sentence the verdict quotes for each.
#:
#: A row may ALSO carry free prose (a node's ``details`` — "Maven
#: execution error: …"). That prose is the ROW's business: it is more
#: informative than any summary, and the row-level view shows it. But
#: the verdict's ``reason`` is QUOTED OUTWARD (the HTML report, the CLI
#: output, the notification body), and a node's free text is not a
#: controlled vocabulary — quoting it would let any node decide what
#: the product says its conclusion was.
#:
#: So the row names its reason by CODE, and the verdict owns the words.
ROW_REASON_NO_EXPERIMENT = "no_experiment"
ROW_REASON_INCONCLUSIVE = "inconclusive"
ROW_REASON_CONTRACT_NOT_APPROVED = "contract_not_approved"
#: The contract lives on a surface outside the JVM and the run did not
#: look at it (#379). A PASS on such a contract says nothing about that
#: surface, so it cannot back an acceptance.
ROW_REASON_EXTERNAL_NOT_OBSERVED = "external_not_observed"

#: code -> the sentence the verdict quotes. The verdict's own vocabulary.
_ROW_REASON_TEXT: dict[str, str] = {
    ROW_REASON_NO_EXPERIMENT: (
        "该契约没有任何实验产出结果; 禁止臆造 PASS/FAIL"
    ),
    ROW_REASON_INCONCLUSIVE: (
        "实验已运行但未得到可判定证据, 保持 UNVERIFIED"
    ),
    ROW_REASON_CONTRACT_NOT_APPROVED: (
        "契约未获批准: 需人工批准后方可作为验收依据"
    ),
    ROW_REASON_EXTERNAL_NOT_OBSERVED: (
        "该契约的外部观测面未被观测（存储不可达或两个时刻不可比）; "
        "此通过不能作为验收依据"
    ),
}


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

    Every reason this policy produces is filed under REASON_BLOCKING or
    REASON_GAP (see the table above); the verdict follows from the kinds
    present, not from whether there is a reason at all.
    """
    matrix = matrix if isinstance(matrix, Mapping) else {}
    raw_rows = matrix.get("rows")
    rows = raw_rows if isinstance(raw_rows, (list, tuple)) else []
    #: (text, kind) — the reason and what it means.
    filed: list[tuple[str, str]] = []

    def file_reason(reason_key: str, /, **fields: Any) -> None:
        """File a DECLARED reason; the table says which side it is on."""
        text, kind = reason_text(reason_key, **fields)
        filed.append((text, kind))

    passed = failed = unverified = 0
    ids: set[str] = set()
    # The contracts that were NEVER APPROVED, derived HERE from the
    # contracts themselves rather than taken from a row's label. The
    # verdict layer can compute this fact, so it computes it: a node that
    # mislabels an unapproved contract as "no experiment" would otherwise
    # make the product say the wrong thing about its own conclusion.
    unapproved: set[str] = set()
    for contract in contracts or ():
        if not isinstance(contract, Mapping):
            continue
        if contract.get("approved") is False:
            cid = str(contract.get("id") or contract.get("contract_id") or "").strip()
            if cid:
                unapproved.add(cid)
    if not rows:
        file_reason("zero_checks")
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping):
            unverified += 1
            file_reason("row_malformed", index=index)
            continue
        cid = str(row.get("contract_id") or row.get("id") or "").strip()
        label = cid or f"第 {index} 条检查"
        duplicate = bool(cid and cid in ids)
        if not cid:
            file_reason("row_without_contract_id", label=label)
        elif duplicate:
            file_reason("duplicate_rows", cid=cid)
        if cid:
            ids.add(cid)
        result = row.get("result")
        if result == "FAIL":
            failed += 1
            # A contract that FAILED is a real problem: something IS
            # wrong, and the answer is "fix it and re-verify".
            file_reason("contract_failed", label=label)
        elif result != "PASS":
            unverified += 1
            # The row names its reason by CODE; the verdict owns the words.
            # A row carrying free prose (a node's `details`) is NOT quoted
            # here — the prose is shown by the row-level view, and letting a
            # node choose the product's outward conclusion is not something
            # the verdict layer should allow.
            #
            # What the verdict layer can COMPUTE wins over what a node
            # LABELLED: an unapproved contract is unapproved whatever the
            # row says about it, and a row that ran no experiment says so
            # in its own experiment record.
            code = (
                ROW_REASON_CONTRACT_NOT_APPROVED if cid in unapproved
                else str(row.get("unverified_reason_code") or "").strip()
            )
            if code not in _ROW_REASON_TEXT:
                # No usable label: derive it from the row's experiment
                # record — the row knows whether an experiment ran.
                experiment_ids = row.get("experiment_ids")
                ran = bool(
                    isinstance(experiment_ids, (list, tuple)) and experiment_ids
                )
                code = (
                    ROW_REASON_INCONCLUSIVE if ran else ROW_REASON_NO_EXPERIMENT
                )
            # The derived code is always a declared one, so there is no
            # generic fallback left to reach for: the verdict can always
            # name WHICH reason applies.
            text = _ROW_REASON_TEXT[code]
            file_reason("row_unverifiable", label=label, text=text)
        else:
            has_evidence = bool(evidence_references(row))
            has_experiment = not require_experiment or bool(
                references(row, "experiment_ids", "experiment_id", "experiment")
            )
            # Did the run LOOK at the surface this contract is about?
            # The matrix row carries the answer (#379); the verdict layer
            # reads it and does no I/O of its own. A row that says the
            # surface was never observed cannot be certified by a PASS
            # that says nothing about that surface — the evidence is
            # missing, not the defect, so this is a GAP and not a
            # blocking reason.
            observed = row.get("observation_decidable") is not False
            if not observed:
                file_reason("external_observation_missing", label=label)
            if not has_evidence:
                file_reason("pass_without_evidence", label=label)
            if not has_experiment:
                file_reason("pass_without_experiment", label=label)
            if has_evidence and has_experiment and observed and cid and not duplicate:
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
                # The declared contract set is itself broken: two rows claim
                # the same contract, or one has no id at all. The coverage
                # map cannot be read, so this is self-contradiction, not a
                # missing measurement.
                file_reason("contract_set_broken")
            if cid:
                expected.add(cid)
        missing = sorted(expected - ids)
        if missing:
            # Coverage gap: the contract is known and nothing was measured
            # for it. Nothing is proven wrong — the evidence is simply not
            # there.
            file_reason("missing_contract_result", ids=", ".join(missing))
            unverified += len(missing)
        unexpected = sorted(ids - expected)
        if unexpected:
            # A check for a contract that does not exist: the two records
            # contradict each other, and a reader cannot tell which is
            # the truth.
            file_reason("row_without_contract", ids=", ".join(unexpected))
        if not expected:
            file_reason("no_valid_contract")

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
                # The summary contradicts the rows it summarises: one of
                # the two is wrong, and a reader cannot tell which.
                file_reason("summary_mismatch", key=key)
    if "total_contracts" in matrix:
        count = matrix["total_contracts"]
        if type(count) is not int or count <= 0 or count > len(ids):
            file_reason("contract_total_mismatch")
    if findings:
        # A confirmed finding is a real problem — the change is wrong.
        file_reason("findings_present", count=len(findings))
    if errors:
        file_reason("pipeline_errors")
    reasons = tuple(dict.fromkeys(text for text, _kind in filed))
    blocking_reasons = tuple(
        dict.fromkeys(text for text, kind in filed if kind == REASON_BLOCKING)
    )
    return VerificationDecision(
        _status_for(
            errors=errors, blocking=blocking_reasons, reasons=reasons
        ),
        reasons, passed, failed, unverified,
        max(len(rows), passed + failed + unverified),
        blocking_reasons,
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
