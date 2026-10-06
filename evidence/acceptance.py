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
    """

    min_recall: float | None = None
    min_precision: float | None = None
    min_f1: float | None = None
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "passed": self.passed,
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


def _metric_failures(
    metrics: Metrics, criteria: AcceptanceCriteria
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
    return reasons


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
    if insufficient:
        return AcceptanceResult(
            status=INSUFFICIENT,
            metrics=metrics,
            counts=counts,
            criteria=criteria,
            insufficient=insufficient,
        )
    failures = _metric_failures(metrics, criteria)
    return AcceptanceResult(
        status=FAIL if failures else PASS,
        metrics=metrics,
        counts=counts,
        criteria=criteria,
        failures=failures,
    )


#: Severity levels the SLO row "BLOCKER/MAJOR Precision>=90%" counts as a
#: severe call. Ground-truth positives in the golden case set are all
#: BLOCKER or MAJOR (16 + 47 of 100); negatives expect no finding at all.
SEVERE_SEVERITIES: frozenset[str] = frozenset({"BLOCKER", "MAJOR"})


def severity_match_of(result: dict[str, Any]) -> bool | None:
    """Ground-truth severity reconciliation for one eval case record.

    ``True``  - a matched positive case whose reported severity is exactly
                the expected one (single value, no drift).
    ``False`` - a matched positive case whose severity drifted or spread
                across several levels: the level call was wrong.
    ``None``  - no level call to judge: an unmatched positive (that is a
                recall miss, not a level error) or a negative case (whose
                wrongness is already counted by ``false_positives``).

    Operates on the per-case record ``cli/specproof/commands/eval.py``
    appends to ``results`` (keys: ``should_detect``, ``matched_findings``,
    ``matched_severities``, ``expected_severity``). Pure, no I/O.
    """
    if not result.get("should_detect"):
        return None
    if not result.get("matched_findings"):
        return None
    severities = [
        s.strip()
        for s in str(result.get("matched_severities") or "").split(",")
        if s.strip() and s.strip() != "—"
    ]
    expected = str(result.get("expected_severity") or "")
    if not expected or not severities:
        return None
    return severities == [expected]


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
                mismatches.append({
                    "case": str(result.get("case", "")),
                    "expected": expected,
                    "actual": str(result.get("matched_severities") or ""),
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
    "fmt_metric",
    "severity_match_of",
    "severity_reconciliation",
]
