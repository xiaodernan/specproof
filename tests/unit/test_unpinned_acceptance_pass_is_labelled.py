"""Gate: an unpinned PASS must say so — on every surface (#223).

``AcceptanceCriteria.default()`` ships with every metric floor ``None``, on
purpose: the module's docstring argues that pinning arbitrary numbers would
itself be a dishonest gate. The consequence is that a PASS asserts only
"the sample was large enough to judge" — nothing about recall or precision.

The first clean end-to-end eval run (2026-10-09) printed exactly that
ambiguity:

    Recall:             66.7%
    Severity agreement: 0.0%
    Acceptance:         PASS          (exit code 0)

...while the CI workflows grepped the same log for ``Recall: 100.0%``. The
tool's verdict and its own gate contradicted each other, and the uploaded HTML
report did not state the verdict at all.

The floor values stay ``None`` — this gate pins the *surface*, not the
thresholds: an unpinned PASS must be labelled as sample-sufficiency only, and
a PASS that did have a floor pinned must stay a bare ``PASS`` so the two can
never be read as the same thing.
"""

from __future__ import annotations

import re
from pathlib import Path

from evidence.acceptance import (
    PASS,
    AcceptanceCriteria,
    AcceptanceResult,
    MetricCounts,
    acceptance_verdict_text,
    evaluate,
)
from evidence.report import render_eval_report

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "cli" / "specproof" / "commands" / "eval.py"

#: The one summary line that states the verdict.
_ACCEPTANCE_ECHO = re.compile(r'click\.echo\(f"Acceptance:\s+\{([^}]*)\}"\)')

#: Present on both surfaces (the report bolds the phrase, so the contiguous
#: fragment is the common piece; the CLI's exact wording is asserted below).
_QUALIFIER = "样本充足"


def _counts() -> MetricCounts:
    """A sample large enough for any floor, with a genuine recall miss."""
    return MetricCounts(
        should_detect=3, detected=2, false_positives=0, negative_cases=1
    )


def _unpinned_pass() -> AcceptanceResult:
    return evaluate(_counts(), AcceptanceCriteria(min_positive_cases=3, min_negative_cases=1))


def _pinned_pass() -> AcceptanceResult:
    """A PASS that DID have a floor pinned: recall 66.7% clears a 50% floor."""
    return evaluate(
        _counts(),
        AcceptanceCriteria(min_recall=50.0, min_positive_cases=3, min_negative_cases=1),
    )


def test_an_unpinned_pass_is_labelled_not_bare() -> None:
    result = _unpinned_pass()
    assert result.status == PASS
    assert result.floors_pinned is False
    text = acceptance_verdict_text(result)
    assert text != PASS, "an unpinned PASS still renders as a bare PASS"
    assert "仅样本充足" in text


def test_a_pinned_pass_stays_bare() -> None:
    result = _pinned_pass()
    assert result.status == PASS
    assert result.floors_pinned is True
    assert acceptance_verdict_text(result) == PASS


def test_non_pass_verdicts_are_never_qualified() -> None:
    """INSUFFICIENT / FAIL already say what they mean."""
    insufficient = evaluate(
        MetricCounts(should_detect=1, detected=1, false_positives=0, negative_cases=0),
        AcceptanceCriteria(min_positive_cases=10, min_negative_cases=5),
    )
    assert insufficient.status == "INSUFFICIENT"
    assert acceptance_verdict_text(insufficient) == "INSUFFICIENT"

    failed = evaluate(_counts(), AcceptanceCriteria(min_recall=100.0))
    assert failed.status == "FAIL"
    assert acceptance_verdict_text(failed) == "FAIL"


def test_the_sidecar_carries_the_flag() -> None:
    """A consumer reading JSON must be able to tell the two PASSes apart."""
    assert _unpinned_pass().to_dict()["floors_pinned"] is False
    assert _pinned_pass().to_dict()["floors_pinned"] is True


def test_the_cli_summary_uses_the_labelled_text() -> None:
    source = EVAL.read_text(encoding="utf-8")
    match = _ACCEPTANCE_ECHO.search(source)
    assert match is not None, "the Acceptance summary line moved — probe broken"
    assert match.group(1).strip() == "acceptance_verdict_text(acceptance)", (
        f"the CLI prints {match.group(1)!r} — an unpinned PASS would read as a "
        "quality verdict again"
    )


def test_the_report_states_the_verdict_and_its_scope() -> None:
    """The uploaded artifact must not need the job log to be read correctly."""
    rows = [{"case": "c", "verdict": "MISS", "should_detect": True}]

    unpinned_html = render_eval_report(rows, _unpinned_pass())
    assert "Acceptance" in unpinned_html
    assert _QUALIFIER in unpinned_html

    pinned_html = render_eval_report(rows, _pinned_pass())
    assert "Acceptance" in pinned_html
    assert _QUALIFIER not in pinned_html, (
        "a PASS that did have a floor pinned must not carry the "
        "sample-sufficiency caveat"
    )


def test_the_report_still_renders_without_an_acceptance() -> None:
    """Backward-compatible: callers that pass only results keep working."""
    html = render_eval_report([{"case": "c", "verdict": "PASS"}])
    assert "SpecProof Evaluation Report" in html
