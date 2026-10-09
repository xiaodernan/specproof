"""Gate: the CI acceptance floors must reach the tool, not live only in a grep (#224).

#222's first clean end-to-end eval run produced a log reading::

    Acceptance:         PASS（仅样本充足：未设 recall/precision/f1 下限）
    Recall:             66.7%
    False positives:    2

with exit code 0, while the two workflow steps that follow grepped that very
log for ``Recall:             100.0%`` and ``False positives:    0`` and failed
on a missing substring. The tool's own verdict and its own gate disagreed, in
the same run, about the same numbers.

``test_ci_acceptance_greps_match_the_eval_summary.py`` already binds the greps
to the tool's *renderer*. This gate binds the other side, which nothing
covered: the contract the workflows assert must be handed to ``eval`` as a
floor it can fail on, so the step that fails names the metric ("recall 66.7
低于下限 100") instead of "substring not found".

Both representations are still allowed to exist — the greps are a cheap second
assertion that survives a tool crash before the summary prints. What is no
longer allowed is a metric asserted only by a grep.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

#: The CLI flag each grepped summary label corresponds to. A metric with no
#: flag cannot be a floor, so asserting it is the defect this gate exists for.
_FLOOR_FLAGS: dict[str, str] = {
    "Recall:": "--min-recall",
    "False positives:": "--max-false-positives",
    "Precision:": "--min-precision",
    "F1 Score:": "--min-f1",
}

_GREP = re.compile(r'grep -q "([A-Za-z ]+:)( *)([^"]*)" eval-run\.log')
#: One continued eval invocation: every ``--flag value`` / ``--flag`` token on
#: the lines of the ``python -m cli.specproof.main eval`` command.
_EVAL_INVOCATION = re.compile(
    r"python -m cli\.specproof\.main eval((?:.*\\\n)*.*?)(?:\n|$)"
)


def _labels_grepped() -> dict[str, set[str]]:
    """workflow -> the summary labels it asserts with a grep."""
    out: dict[str, set[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        labels = {label for label, _pad, _val in _GREP.findall(path.read_text(encoding="utf-8"))}
        if labels:
            out[path.name] = labels
    assert out, "no eval-log greps found — the workflows changed shape"
    return out


def _floor_flags_per_workflow() -> dict[str, set[str]]:
    """workflow -> every acceptance floor flag passed to ``eval`` in it."""
    out: dict[str, set[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        flags: set[str] = set()
        for command in _EVAL_INVOCATION.findall(text):
            # Values are matched separately: a ``--flag`` carrying no value is
            # still a flag, and must not be read as one carrying the next.
            flags.update(re.findall(r"(--min-[a-z-]+|--max-false-positives)", command))
        out[path.name] = flags
    return out


def test_every_grepped_metric_is_also_a_floor_the_tool_enforces() -> None:
    flags = _floor_flags_per_workflow()
    for workflow, labels in _labels_grepped().items():
        for label in sorted(labels):
            flag = _FLOOR_FLAGS.get(label)
            assert flag is not None, (
                f"{workflow}: greps the {label!r} summary line but this gate "
                f"has no floor flag mapped for it ({sorted(_FLOOR_FLAGS)}) — "
                f"add the CLI flag, or drop the grep for a metric the tool "
                f"cannot enforce"
            )
            assert flag in flags[workflow], (
                f"{workflow}: asserts {label.strip()} by grep only. {flag} "
                f"exists on the CLI but this invocation does not pass it, so "
                f"`eval --gate` reports PASS while the grep fails (#222). "
                f"Flags passed: {sorted(flags[workflow]) or 'none'}"
            )


def test_the_gated_workflows_pass_the_gate_flag() -> None:
    """A floor without ``--gate`` does not fail the step.

    ``--min-recall 100`` alone only appears in the summary; the exit code is
    driven by ``--gate``. Passing floors into an ungated invocation would look
    like the contract is enforced while the run still exits 0.
    """
    for workflow, labels in _labels_grepped().items():
        assert "--min-recall" in _floor_flags_per_workflow()[workflow], (
            f"{workflow}: {sorted(labels)} asserted but no recall floor passed"
        )
        text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
        assert "--gate" in text, (
            f"{workflow}: passes acceptance floors without --gate, so a "
            f"breached floor cannot fail the step"
        )
