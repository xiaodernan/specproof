"""Gate: the CI acceptance greps must match the eval's own summary (#218).

Both workflows assert the eval verdict with two text greps against the
captured log — four hand copies of one fact:

    ci.yml            grep -q "Recall:             100.0%" eval-run.log
                      grep -q "False positives:    0" eval-run.log
    nightly-eval.yml  the same two strings

Each is a copy of the summary the CLI prints: the label, the column padding
that aligns every value at column 21, and the value rendering
(``fmt_metric(100.0)`` is ``"100.0%"``). Nothing binds any of the copies, so a
reformat of the summary — or a change to ``fmt_metric`` — breaks the product's
acceptance gate for a reason that has nothing to do with the product: the
step then fails on a missing substring, and the failure message ("Recall gate
FAILED" / "NIGHTLY EVAL REGRESSION") points at the wrong thing.

This is the third instance of the family #216/#217 closed in the docs (a
hand-copied representation of one fact, with no gate) — and it is the same
shape #203 found in these very two files, where a fix landed in ci.yml and
was never propagated to nightly-eval.yml. So the gate does not just bind each
string to the tool; it also requires every workflow that asserts the contract
to assert the *same* strings, which is exactly the divergence #203 hit.

The fix does not touch the workflows: the strings are derived from the tool's
own source and formatter, so the copies can only move together.
"""

from __future__ import annotations

import re
from pathlib import Path

from evidence.acceptance import fmt_metric

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "cli" / "specproof" / "commands" / "eval.py"
WORKFLOWS = ROOT / ".github" / "workflows"

#: A single-line summary echo: the literal prefix (label + padding) then the
#: interpolated value. Multi-line echoes (implicit concatenation) do not
#: match, which is fine — the greps target single-line ones.
_ECHO = re.compile(r'click\.echo\(f"([A-Za-z ]+:)( *)\{([^}]*)\}"\)')
_GREP = re.compile(r'grep -q "([^"]+)" eval-run\.log')


def _summary_prefixes() -> dict[str, str]:
    """label -> the exact literal prefix the CLI prints before the value."""
    out: dict[str, str] = {}
    for label, pad, _expr in _ECHO.findall(EVAL.read_text(encoding="utf-8")):
        out[label.strip()] = label + pad
    # A collapsed parse must not read as "no problem".
    assert len(out) >= 6, f"summary parse collapsed: {sorted(out)}"
    for required in ("Recall:", "False positives:"):
        assert required in out, f"summary label {required!r} moved — probe broken"
    return out


def _greps_by_workflow() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        patterns = _GREP.findall(path.read_text(encoding="utf-8"))
        if patterns:
            out[path.name] = patterns
    assert len(out) >= 2, (
        f"expected the eval-log acceptance greps in >=2 workflows, found "
        f"{sorted(out)} — the gate steps moved or were rewritten"
    )
    return out


def _label_of(pattern: str, prefixes: dict[str, str]) -> str:
    matched = [lab for lab, pre in prefixes.items() if pattern.startswith(pre)]
    assert len(matched) == 1, (
        f"grep pattern {pattern!r} does not start with exactly one summary "
        f"prefix the CLI prints {sorted(prefixes)} — the label or its column "
        "padding drifted on one side only"
    )
    return matched[0]


def test_every_grep_reuses_the_summary_label_and_padding() -> None:
    prefixes = _summary_prefixes()
    for workflow, patterns in _greps_by_workflow().items():
        for pattern in patterns:
            label = _label_of(pattern, prefixes)
            prefix = prefixes[label]
            assert pattern.startswith(prefix), (workflow, pattern)
            # A pattern with *more* padding than the CLI prints still starts
            # with the shorter prefix, so the check above alone does not test
            # padding. The extra space would then be read as part of the value
            # and only the value clause would fire — which reports the wrong
            # cause. This clause keeps "padding drifted" diagnostic.
            assert not pattern.startswith(prefix + " "), (
                f"{workflow}: {pattern!r} has more padding after {label!r} "
                f"than the CLI prints ({prefix!r})"
            )


def test_every_grep_asserts_a_value_the_tool_renders() -> None:
    prefixes = _summary_prefixes()
    seen: dict[str, str] = {}
    for patterns in _greps_by_workflow().values():
        for pattern in patterns:
            label = _label_of(pattern, prefixes)
            seen[label] = pattern[len(prefixes[label]):]

    # Perfect recall renders through the same formatter the summary uses — if
    # fmt_metric changes shape, the greps must change with it.
    assert seen.get("Recall:") == fmt_metric(100.0), (
        f"the recall grep asserts {seen.get('Recall:')!r} but the tool renders "
        f"perfect recall as {fmt_metric(100.0)!r}"
    )
    assert seen.get("False positives:") == str(0), (
        f"the false-positive grep asserts {seen.get('False positives:')!r} "
        f"but the counter renders as {str(0)!r}"
    )


def test_no_workflow_is_left_behind_with_a_different_contract() -> None:
    """The #203 shape: a fix that lands in one workflow and not the other.

    Every workflow that asserts the eval contract must assert the same
    strings — a workflow carrying only the recall clause, or a stale copy of
    either, is a weaker gate than the one next to it and reads as if the
    product were covered.
    """
    by_workflow = _greps_by_workflow()
    reference_name, reference = next(iter(by_workflow.items()))
    for workflow, patterns in by_workflow.items():
        assert sorted(patterns) == sorted(reference), (
            f"{workflow} asserts a different eval contract than "
            f"{reference_name}: {sorted(patterns)} vs {sorted(reference)}"
        )
