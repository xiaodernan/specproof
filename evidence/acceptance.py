"""Acceptance scoring — one honest, enforceable Recall/Precision gate.

The evaluation CLI (`cli/specproof/commands/eval.py`), the HTML report
(`evidence/report.py`) and the diff-only baseline comparison
(`cli/specproof/commands/baseline.py`) all used to compute
``recall``/``precision`` with the same inline expression:

    recall = detected / should_detect * 100 if should_detect > 0 else 100.0

The ``else 100.0`` is the bug this module removes: a benchmark that
contains **no positive cases** (``should_detect == 0``) has an undefined
recall, not a flawless one. Reporting ``Recall: 100.0%`` for an empty or
degenerate sample asserts a benign result the data cannot support — the
same "a read failure must never render as an honest empty state" class of
defect the frontend already guards. An acceptance verdict built on such a
number (e.g. "PASS, recall 100%") would certify a model on zero evidence.

So every metric here is ``float | None``: ``None`` means "not computable
from this sample" and is always surfaced as such, never coerced to 100.
``evaluate`` additionally refuses to emit a PASS when the sample is too
small to mean anything (``INSUFFICIENT``), so an acceptance gate cannot be
passed by shrinking the evaluation set to nothing.

Pure and side-effect free: no pipeline, no Docker, no model — it operates
on counts, which makes the whole gate offline unit-testable with synthetic
numbers (see ``tests/unit/test_acceptance_gate.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The three verdicts an acceptance run can produce.
PASS = "PASS"
FAIL = "FAIL"
INSUFFICIENT = "INSUFFICIENT"
ACCEPTANCE_STATUSES: frozenset[str] = frozenset({PASS, FAIL, INSUFFICIENT})


@dataclass(frozen=True)
class MetricCounts:
    """Raw per-run tallies feeding the acceptance metrics.

    ``should_detect``  — number of positive (should-detect) cases in the set.
    ``detected``       — positive cases the pipeline matched (true positives).
    ``false_positives``— negative cases that produced a confirmed finding.
    ``negative_cases`` — number of negative cases in the set (a guard: a
                         set with no negatives cannot evidence a precision
                         floor, since precision is never challenged).
    ``detected_any``   — positive cases matched by *any* contract (a looser
                         recall variant carried by the baseline comparison).
    """

    should_detect: int
    detected: int
    false_positives: int
    negative_cases: int = 0
    detected_any: int = 0


@dataclass(frozen=True)
class Metrics:
    """Computed metrics; ``None`` means "undefined for this sample"."""

    recall: float | None
    precision: float | None
    f1: float | None
    recall_any: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "recall": self.recall,
            "precision": self.precision,
            "f1": self.f1,
            "recall_any": self.recall_any,
        }


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def score(counts: MetricCounts) -> Metrics:
    """Compute recall / precision / F1 from counts.

    Formulas are preserved exactly as the historical CLI/report code used
    them (``precision = detected / (detected + false_positives)``); only the
    zero-denominator behaviour changed — such a metric is now ``None``
    instead of a misleading ``100.0``. F1 is ``None`` unless BOTH recall and
    precision are defined, so it can never look computed from a partial
    sample.
    """
    recall = _pct(counts.detected, counts.should_detect)
    precision = _pct(counts.detected, counts.detected + counts.false_positives)
    recall_any = _pct(counts.detected_any, counts.should_detect)
    if recall is None or precision is None:
        f1: float | None = None
    elif recall + precision == 0:
        f1 = 0.0
    else:
        f1 = round(2 * recall * precision / (recall + precision), 1)
    return Metrics(recall=recall, precision=precision, f1=f1, recall_any=recall_any)


@dataclass(frozen=True)
class AcceptanceCriteria:
    """Floors and sample-size guards for an acceptance decision.

    Every threshold is explicit; there is no implicit "anything passes by
    default". ``min_positive_cases`` / ``min_negative_cases`` are the sample
    floors below which the run is INSUFFICIENT (not a pass, not a fail) —
    this is what stops a small or empty evaluation set from certifying a
    verdict it cannot support.

    ``max_false_positives`` is the one *ceiling*: "no false positives" cannot
    be expressed as a ``min_`` floor, and until it existed here the CI
    workflows had to assert that contract by grepping the CLI's own log text
    (#224). A gate that lives only in a grep is a gate the tool's verdict
    cannot honour: ``eval --gate`` printed PASS and exited 0 next to
    ``False positives: 2`` while the workflow failed on a missing substring
    whose message named no metric.
    """

    min_recall: float | None = None
    min_precision: float | None = None
    min_f1: float | None = None
    #: Most confirmed findings on negative cases the run may produce. ``None``
    #: means the false-positive rate is not part of the contract — it is *not*
    #: an implicit "any number of false positives is fine", because a run with
    #: zero negative cases produces zero false positives regardless of quality.
    max_false_positives: int | None = None
    min_positive_cases: int = 1
    min_negative_cases: int = 0

    @classmethod
    def default(cls) -> AcceptanceCriteria:
        """A conservative starting contract for the golden case set.

        Floors stay ``None`` (i.e. only sample sufficiency is enforced) until
        a maintainer pins agreed numbers from a real full-suite run — a
        default that silently passes recall >= 0 or fails on an unset floor
        would itself be a dishonest gate.
        """
        return cls(min_positive_cases=10, min_negative_cases=5)

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_recall": self.min_recall,
            "min_precision": self.min_precision,
            "min_f1": self.min_f1,
            "max_false_positives": self.max_false_positives,
            "min_positive_cases": self.min_positive_cases,
            "min_negative_cases": self.min_negative_cases,
        }


@dataclass(frozen=True)
class AcceptanceResult:
    """Verdict + the honest reasons behind it, ready for CLI / JSON / UI."""

    status: str
    metrics: Metrics
    counts: MetricCounts
    criteria: AcceptanceCriteria
    failures: list[str] = field(default_factory=list)
    insufficient: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == PASS

    @property
    def floors_pinned(self) -> bool:
        """True when at least one metric floor was actually requested.

        With every floor left ``None`` (the shipped default, deliberately —
        see ``AcceptanceCriteria.default``) a PASS asserts only that the
        sample was large enough. It says nothing about recall or precision,
        so it must not be surfaced as a bare "PASS" (#223).
        """
        return any(
            floor is not None
            for floor in (
                self.criteria.min_recall,
                self.criteria.min_precision,
                self.criteria.min_f1,
                self.criteria.max_false_positives,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "passed": self.passed,
            "floors_pinned": self.floors_pinned,
            "metrics": self.metrics.to_dict(),
            "counts": {
                "should_detect": self.counts.should_detect,
                "detected": self.counts.detected,
                "false_positives": self.counts.false_positives,
                "negative_cases": self.counts.negative_cases,
                "detected_any": self.counts.detected_any,
            },
            "criteria": self.criteria.to_dict(),
            "failures": list(self.failures),
            "insufficient": list(self.insufficient),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceResult:
        """Rebuild a verdict from the dict ``to_dict`` wrote.

        The sidecar stores the verdict so a reader never has to re-derive
        it. This is the other direction: rebuild it exactly, so that a
        report can be re-rendered from a sidecar alone - the evidence
        stays the evidence and the report becomes a VIEW of it, instead
        of a frozen artifact of whichever build happened to run
        (ledger #411).
        """
        metrics = data.get("metrics") or {}
        counts = data.get("counts") or {}
        criteria = data.get("criteria") or {}
        return cls(
            status=str(data.get("status") or INSUFFICIENT),
            metrics=Metrics(
                recall=metrics.get("recall"),
                precision=metrics.get("precision"),
                f1=metrics.get("f1"),
                recall_any=metrics.get("recall_any"),
            ),
            counts=MetricCounts(
                should_detect=int(counts.get("should_detect") or 0),
                detected=int(counts.get("detected") or 0),
                false_positives=int(counts.get("false_positives") or 0),
                negative_cases=int(counts.get("negative_cases") or 0),
                detected_any=int(counts.get("detected_any") or 0),
            ),
            criteria=AcceptanceCriteria(
                min_recall=criteria.get("min_recall"),
                min_precision=criteria.get("min_precision"),
                min_f1=criteria.get("min_f1"),
                max_false_positives=criteria.get("max_false_positives"),
                min_positive_cases=int(criteria.get("min_positive_cases") or 0),
                min_negative_cases=int(criteria.get("min_negative_cases") or 0),
            ),
            failures=[str(f) for f in (data.get("failures") or [])],
            insufficient=[str(s) for s in (data.get("insufficient") or [])],
        )


def _metric_failures(
    metrics: Metrics, criteria: AcceptanceCriteria, counts: MetricCounts
) -> list[str]:
    checks = [
        ("recall", metrics.recall, criteria.min_recall),
        ("precision", metrics.precision, criteria.min_precision),
        ("f1", metrics.f1, criteria.min_f1),
    ]
    reasons: list[str] = []
    for name, value, floor in checks:
        if floor is None:
            continue
        if value is None:
            reasons.append(
                f"{name} 无法评估（样本分母为 0），无法满足下限 {floor}"
            )
        elif value < floor:
            reasons.append(f"{name} {value} 低于下限 {floor}")
    if criteria.max_false_positives is not None:
        ceiling = criteria.max_false_positives
        if counts.false_positives > ceiling:
            reasons.append(
                f"误报 {counts.false_positives} 超过上限 {ceiling}"
                f"（负例被误判为已发现问题）"
            )
    return reasons


def _no_negatives_ceiling_reason(ceiling: int, negative_cases: int) -> str:
    """Why a requested false-positive ceiling cannot be honoured.

    A ceiling can only be breached by a negative case, so honouring one
    over a negative-free set would certify a constraint never exercised
    (#225). Returned as INSUFFICIENT rather than PASS: the floors cannot
    raise this, because ``min_negative_cases`` defaults to 0 precisely so
    a positive-only set stays gradeable.

    The wording must not report a breach. Nothing was measured against
    the ceiling -- that absence of measurement IS this verdict -- so a
    reason reading "误报 超过上限 N" would announce a failure the run did
    not produce, which is the exact dishonesty #225 removed and the one
    #226's own wording edit put back. It reports the bound as unexercised.
    """
    return (
        f"负例样本 {negative_cases}，误报上限 {ceiling} 无从验证"
        f"（误报只可能由负例触发；无负例时该上限不构成任何约束，"
        f"既未达标也未超限，故判样本不足而非通过）"
    )

def evaluate(
    counts: MetricCounts, criteria: AcceptanceCriteria
) -> AcceptanceResult:
    """Score the counts, then decide PASS / FAIL / INSUFFICIENT.

    Sample sufficiency is checked FIRST: a set that is too small to
    demonstrate the requested floors returns INSUFFICIENT even when its
    (undefined or trivially perfect) metrics would otherwise "pass". Only a
    sufficient sample can produce PASS or FAIL.
    """
    metrics = score(counts)
    insufficient: list[str] = []
    if counts.should_detect < criteria.min_positive_cases:
        insufficient.append(
            f"正例样本 {counts.should_detect} < 要求的最小正例数 "
            f"{criteria.min_positive_cases}（样本不足，无法判定召回率）"
        )
    if counts.negative_cases < criteria.min_negative_cases:
        insufficient.append(
            f"负例样本 {counts.negative_cases} < 要求的最小负例数 "
            f"{criteria.min_negative_cases}（样本不足，无法验证误报率下限）"
        )
    if criteria.max_false_positives is not None and counts.negative_cases == 0:
        # A ceiling can only ever be breached by a negative case, so a run with
        # no negatives cannot breach it at any quality: max_false_positives=0
        # would print PASS having tested nothing (#225). The floors cannot raise
        # this -- min_negative_cases defaults to 0 precisely so a positive-only
        # set stays gradeable -- so the ceiling itself has to insist.
        insufficient.append(
            _no_negatives_ceiling_reason(
                criteria.max_false_positives, counts.negative_cases
            )
        )

    if insufficient:
        return AcceptanceResult(
            status=INSUFFICIENT,
            metrics=metrics,
            counts=counts,
            criteria=criteria,
            insufficient=insufficient,
        )
    failures = _metric_failures(metrics, criteria, counts)
    return AcceptanceResult(
        status=FAIL if failures else PASS,
        metrics=metrics,
        counts=counts,
        criteria=criteria,
        failures=failures,
    )


def acceptance_verdict_text(result: AcceptanceResult) -> str:
    """The verdict, plus what it actually asserts — never a bare "PASS" (#223).

    ``AcceptanceCriteria.default()`` ships with every metric floor ``None``, so
    the shipped PASS means "the sample was large enough to judge" and nothing
    more. Printed bare, it reads as "quality is fine": the first clean
    end-to-end eval run (2026-10-09) showed ``Acceptance: PASS`` next to
    ``Recall: 66.7%`` and ``Severity agreement: 0.0%`` with exit code 0, while
    the CI workflows grepped the same log for ``Recall: 100.0%`` — the tool's
    verdict and its own gate contradicted each other.

    The floor values themselves stay ``None``: pinning arbitrary numbers would
    be the dishonest gate ``AcceptanceCriteria.default`` warns about. What
    changes is the *surface* — an unpinned PASS is labelled as such.
    """
    if result.status != PASS or result.floors_pinned:
        return result.status
    return f"{PASS}（仅样本充足：未设 recall/precision/f1 下限）"


#: Severity levels the SLO row "BLOCKER/MAJOR Precision>=90%" counts as a
#: severe call. Ground-truth positives in the golden case set are all
#: BLOCKER or MAJOR (16 + 47 of 100); negatives expect no finding at all.
SEVERE_SEVERITIES: frozenset[str] = frozenset({"BLOCKER", "MAJOR"})

#: Severity strength, strongest first. The SAME order the matrix policy
#: uses when it picks the strongest finding for a contract
#: (``agent/matrix_policy.py``: ``_court_sort_key``): a reader acts on the
#: strongest level reported for a contract, so the strongest level is what
#: a level call is judged on.
SEVERITY_RANK: dict[str, int] = {
    "BLOCKER": 4,
    "MAJOR": 3,
    "MINOR": 2,
    "INFORMATIONAL": 1,
}


def severity_rank(level: object) -> int:
    """How strong a level is; unknown levels rank 0 (below every known one)."""
    return SEVERITY_RANK.get(str(level or "").strip().upper(), 0)


def strongest_severity(levels: list[str]) -> str:
    """The strongest level among the given ones ('' when there is none)."""
    best = ""
    best_rank = 0
    for level in levels:
        rank = severity_rank(level)
        if rank > best_rank:
            best = str(level).strip().upper()
            best_rank = rank
    return best


def _levels_for_expected_contract(result: dict[str, Any]) -> list[str]:
    """The levels reported for the contract this case is about.

    Prefers the per-finding evidence (which says WHICH contract each
    finding is about) and falls back to the flat ``matched_severities``
    string when a record carries no per-finding breakdown.
    """
    evidence = result.get("finding_evidence")
    contract = str(result.get("expected_contract") or "").strip()
    if isinstance(evidence, list) and evidence:
        own = [
            str(item.get("severity") or "")
            for item in evidence
            if isinstance(item, dict)
            and (not contract or str(item.get("contract_id") or "").strip() == contract)
        ]
        if own:
            return own
    return [
        s.strip()
        for s in str(result.get("matched_severities") or "").split(",")
        if s.strip() and s.strip() != "—"
    ]


def severity_match_of(result: dict[str, Any]) -> bool | None:
    """Ground-truth severity reconciliation for one eval case record.

    ``True``  - a matched positive case whose STRONGEST reported level for
                the expected contract is the expected one.
    ``False`` - a matched positive case whose strongest level differs from
                the expected one: the level call was wrong.
    ``None``  - no level call to judge: an unmatched positive (that is a
                recall miss, not a level error) or a negative case (whose
                wrongness is already counted by ``false_positives``).

    Why the STRONGEST level and not "the only level": one contract can
    carry more than one confirmed finding (a static source diff AND an
    execution differential for the same contract), and then the levels
    differ per FINDING while the contract has one level. The repo's own
    matrix policy already resolves that by picking the strongest finding
    for a contract (``agent/matrix_policy.py``: ``_court_sort_key``), so
    the metric must judge the same level the matrix shows. Judging the
    whole list instead counted a correct BLOCKER as a drift whenever a
    weaker duplicate existed for the same contract (ledger #395).

    Operates on the per-case record ``cli/specproof/commands/eval.py``
    appends to ``results`` (keys: ``should_detect``, ``matched_findings``,
    ``matched_severities``, ``expected_severity``, ``expected_contract``,
    ``finding_evidence``). Pure, no I/O.
    """
    if not result.get("should_detect"):
        return None
    if not result.get("matched_findings"):
        return None
    levels = _levels_for_expected_contract(result)
    expected = str(result.get("expected_severity") or "")
    if not expected or not levels:
        return None
    return strongest_severity(levels) == expected.strip().upper()


def severity_levels_of(result: dict[str, Any]) -> list[str]:
    """The levels reported for this case's expected contract (see above)."""
    return _levels_for_expected_contract(result)


def severity_reconciliation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate ground-truth severity reconciliation over eval results.

    Two honest numbers close the SLO row "BLOCKER/MAJOR Precision>=90%"
    (whose yellow read was "true precision needs ground truth"):

    - ``severity_agreement`` - of the matched positive cases, the share
      whose reported severity is exactly the expected one. This judges the
      *level* call; a MISS is a recall failure and stays out of the
      denominator (it never made a level call to be wrong).
    - ``severe_precision`` - the share of *severe calls* the ground truth
      endorses. A severe call is a matched positive case whose expected
      severity is BLOCKER/MAJOR (at any reported level: a MAJOR finding
      downgraded to MINOR is still a wrong severe call) plus a negative
      case that produced any confirmed finding - the same FP the
      case-level precision already counts, because a confirmed finding on
      a clean PR is a wrong verdict at any level. Positives expecting
      lower severities never enter the denominator (they made no severe
      call to be right or wrong about). ``None`` when the denominator
      is 0.

    Both are ``None`` on an empty sample, mirroring ``score``: an
    unevaluated metric must never render as a high score.
    """
    matched = 0
    agreed = 0
    mismatches: list[dict[str, str]] = []
    tp = 0
    severe_domain = 0
    fp = 0
    for result in results:
        match = severity_match_of(result)
        if match is not None:
            matched += 1
            expected = str(result.get("expected_severity") or "")
            if expected in SEVERE_SEVERITIES:
                severe_domain += 1
                if match:
                    tp += 1
            if match:
                agreed += 1
            else:
                levels = severity_levels_of(result)
                # "got" is the level the case was JUDGED on: the strongest
                # level for the case's own contract. The flat
                # matched_severities list spans every contract the run
                # matched, so it can name a level this case was never
                # judged on - it is context, not the verdict. Rendering it
                # as "got" made the drift line disagree with the judgement
                # (ledger #411).
                strongest = strongest_severity(levels)
                mismatches.append({
                    "case": str(result.get("case", "")),
                    "expected": expected,
                    "actual": strongest or str(result.get("matched_severities") or ""),
                    "reported": str(result.get("matched_severities") or ""),
                    "contract": str(result.get("expected_contract") or ""),
                    # The strongest level is what the case is judged on, and
                    # the levels it came from say WHY it drifted: the tool
                    # derives the level from the evidence path it took (ADR
                    # -004: BLOCKER needs execution + DB evidence), so a
                    # drift is a statement about the EVIDENCE, not about
                    # the defect. Reporting the evidence kind makes that
                    # readable instead of leaving a bare "expected X, got
                    # Y" that looks like the tool guessed.
                    "strongest": strongest_severity(levels),
                    "evidence_kinds": ",".join(
                        sorted({
                            str(item.get("evidence_type") or "")
                            for item in (result.get("finding_evidence") or [])
                            if isinstance(item, dict)
                            and str(item.get("evidence_type") or "")
                        })
                    ),
                })
        if (
            not result.get("should_detect")
            and result.get("verdict") == "FALSE_POSITIVE"
        ):
            fp += 1
    return {
        "severity_agreement": _pct(agreed, matched),
        "severe_precision": _pct(tp, severe_domain + fp),
        "matched_positive_cases": matched,
        "severity_mismatch_cases": len(mismatches),
        "mismatches": mismatches,
        "severe_true_positives": tp,
        "severe_call_positives": severe_domain,
        "severe_false_positives": fp,
    }


def fmt_metric(value: float | None, *, undefined: str = "无法评估") -> str:
    """Render a metric honestly for a human surface.

    ``None`` never becomes a number: it shows the ``undefined`` word (with a
    "n=0" hint) so a reader cannot mistake an unevaluated metric for a high
    score. Callers that want their own wording pass ``undefined``.
    """
    if value is None:
        return undefined + " (n=0)"
    return f"{value}%"


__all__ = [
    "PASS",
    "FAIL",
    "INSUFFICIENT",
    "ACCEPTANCE_STATUSES",
    "SEVERE_SEVERITIES",
    "MetricCounts",
    "Metrics",
    "AcceptanceCriteria",
    "AcceptanceResult",
    "score",
    "evaluate",
    "acceptance_verdict_text",
    "fmt_metric",
    "severity_match_of",
    "severity_reconciliation",
]
