"""#251 — how trustworthy is the eval verdict? Derive it from the files, not memory.

#248 measured a perfect-looking four-case run (Recall/Precision 100%) that ended
`Acceptance: INSUFFICIENT`: 3 positives < 10 and 1 negative < 5. That verdict is
correct, and its cause is structural rather than incidental — the CI subset is
only four cases, and CI deliberately weakens its sample floors to match.

These tests pin the sample arithmetic so the numbers can never be misquoted in
either direction:

* the four-case subset structurally CANNOT meet the default floors, so a green
  CI gate is not a 10/5-backed verdict and must not be read as one;
* the shipped golden pool DOES meet them after holdout isolation, so a trusted
  verdict is achievable — the honest path is the full pool, not weaker floors;
* a perfect 3/1 run is INSUFFICIENT, never a vacuous PASS.

Every count is re-derived from `golden-cases/` and the CI workflow file, so the
claims re-verify themselves whenever the pool or the workflow changes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from agent.holdout import HoldoutRegistry
from evidence.acceptance import (
    AcceptanceCriteria,
    MetricCounts,
    evaluate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = REPO_ROOT / "golden-cases"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# The defaults the CLI documents for `specproof eval --gate`; they are the
# floors a "Recall: 100%" headline is entitled to claim.
DEFAULT_MIN_POSITIVE = 10
DEFAULT_MIN_NEGATIVE = 5


def _case_dirs() -> list[Path]:
    return sorted(d for d in GOLDEN.iterdir() if d.is_dir() and d.name.startswith("case-"))


def _pool_composition(dirs: list[Path]) -> tuple[int, int]:
    positives = negatives = 0
    for d in dirs:
        gt = d / "ground-truth.json"
        if not gt.exists():
            continue
        if json.loads(gt.read_text(encoding="utf-8")).get("should_detect"):
            positives += 1
        else:
            negatives += 1
    return positives, negatives


def _ci_subset_names() -> list[str]:
    """The four cases CI actually copies, read out of the workflow file."""
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    return re.findall(r"cp -r golden-cases/(case-[A-Za-z0-9-]+)", text)


def _ci_floors() -> tuple[int, int]:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    positive = re.search(r"--min-positive-cases\s+(\d+)", text)
    negative = re.search(r"--min-negative-cases\s+(\d+)", text)
    if positive is None or negative is None:
        raise AssertionError(
            "CI no longer passes explicit sample floors — the statistical basis "
            "of a green gate changed; re-derive what it is entitled to claim"
        )
    return int(positive.group(1)), int(negative.group(1))


def test_the_four_case_ci_subset_can_never_meet_the_default_floors() -> None:
    subset = _ci_subset_names()
    assert subset, "CI copies case dirs into eval-subset — none parsed"
    positives, negatives = _pool_composition([GOLDEN / n for n in subset])

    # The measured shape of #248's run, re-derived rather than remembered.
    assert (positives, negatives) == (3, 1), (
        f"CI subset composition changed to {positives}/{negatives}; "
        "re-check what the four-case verdict is entitled to claim"
    )
    assert positives < DEFAULT_MIN_POSITIVE, (
        "a subset this small was expected to be structurally below the "
        "default positive floor — if it now clears it, the floors changed"
    )
    assert negatives < DEFAULT_MIN_NEGATIVE


def test_ci_weakens_its_floors_to_exactly_what_the_subset_can_meet() -> None:
    """The reason a 4-case gate can print a verdict at all.

    If CI ever used the DEFAULT floors, every green gate would silently become
    INSUFFICIENT; if it used floors BELOW what the subset meets, the gate would
    be vacuous. This pins the deliberate middle.
    """
    subset = _ci_subset_names()
    positives, negatives = _pool_composition([GOLDEN / n for n in subset])
    ci_positive, ci_negative = _ci_floors()

    assert (ci_positive, ci_negative) != (DEFAULT_MIN_POSITIVE, DEFAULT_MIN_NEGATIVE), (
        "CI is not running the default sample floors"
    )
    assert positives >= ci_positive and negatives >= ci_negative, (
        "the weakened floors must be exactly satisfiable by the subset, or the "
        "gate can never pass and would be vacuous noise"
    )
    # A four-case subset has too few negatives to say anything about the
    # false-positive ceiling, which is why one of them is only 1.
    assert ci_negative < DEFAULT_MIN_NEGATIVE


def test_the_shipped_golden_pool_can_meet_the_default_floors_after_isolation() -> None:
    """The honest path to a trusted verdict: run the pool, not fewer floors."""
    registry = HoldoutRegistry.load()
    kept = [d for d in _case_dirs() if not registry.is_holdout(d.name)]
    positives, negatives = _pool_composition(kept)

    assert positives >= DEFAULT_MIN_POSITIVE, f"only {positives} positives left"
    assert negatives >= DEFAULT_MIN_NEGATIVE, f"only {negatives} negatives left"


def test_a_perfect_three_positive_run_is_insufficient_not_a_vacuous_pass() -> None:
    """#248's run, re-scored: 3/3 detected, 0 false positives, 1 negative.

    A naive implementation would print `Recall: 100% / Precision: 100%` and
    pass the gate. The sample sufficiency check must refuse first, so a green
    gate can never be earned by a sample too small to earn it.
    """
    result = evaluate(
        MetricCounts(should_detect=3, detected=3, false_positives=0, negative_cases=1),
        AcceptanceCriteria(
            min_recall=None,
            min_precision=None,
            min_f1=None,
            max_false_positives=0,
            min_positive_cases=DEFAULT_MIN_POSITIVE,
            min_negative_cases=DEFAULT_MIN_NEGATIVE,
        ),
    )

    assert result.status == "INSUFFICIENT"
    assert result.metrics.recall == 100.0, "the metric is perfect but the sample is not"
    assert result.metrics.precision == 100.0
    assert not result.passed, "INSUFFICIENT must never report as a pass"
    assert len(result.insufficient) == 2, result.insufficient
