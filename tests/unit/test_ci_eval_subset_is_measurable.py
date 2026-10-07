"""#205 — the CI eval subset must be real cases the gate can actually measure.

`ci.yml`'s "Evaluate representative golden-case subset" step copies four golden
cases into `eval-subset/` and then gates on two greps of the summary:

    grep -q "Recall:             100.0%" eval-run.log
    grep -q "False positives:    0"     eval-run.log

Three things were wrong with that, and they compound:

1. **Two of the four copied cases were holdout.** `case-01-auth-bypass` and
   `case-10-comment-only` are declared in `docs/eval/holdout-manifest.json`, and
   isolation is ON by default (`plan_case_dirs`), so both were silently dropped:
   the run went from 4 cases to 2. The subset's own comment promised a "static
   positive, negative, execution-only positive, new-category execution case".
2. **The case it lost was the only NEGATIVE one.** With zero negative cases,
   `False positives: 0` is true no matter what the tool does — the second gate
   clause could not fail. A gate that cannot fail is not a gate.
3. **The tool's own gate was unused.** `eval` has `--gate`, which exits
   non-zero unless the acceptance status is PASS and enforces explicit sample
   floors. The workflow greps two lines instead, so a run the tool itself calls
   `INSUFFICIENT` (too few cases to judge recall) still passed.

These clauses are written against the workflow text and the manifest, so a
future edit that reintroduces a holdout case, drops the negative control, or
drops `--gate` fails here rather than in a silently-green CI job.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"
MANIFEST = REPO / "docs" / "eval" / "holdout-manifest.json"
GOLDEN = REPO / "golden-cases"

_COPIED_RE = re.compile(r"cp -r golden-cases/(case-[\w\-]+) eval-subset/")


def ci_source() -> str:
    return CI.read_text(encoding="utf-8")


def copied_cases() -> list[str]:
    cases = _COPIED_RE.findall(ci_source())
    assert len(cases) >= 2, (
        f"found {cases} in the CI eval subset — the step or its shape moved"
    )
    return cases


def holdout_cases() -> set[str]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {row["case_id"] for row in data["cases"]}


def is_negative(case: str) -> bool:
    truth = json.loads((GOLDEN / case / "ground-truth.json").read_text(encoding="utf-8"))
    return not truth.get("should_detect", False)


def test_every_copied_case_exists_and_is_not_holdout() -> None:
    """A holdout case in the subset is silently dropped — that is how the
    negative control vanished without anyone noticing."""
    held = holdout_cases()
    for case in copied_cases():
        assert (GOLDEN / case).is_dir(), f"{case} does not exist under golden-cases/"
        assert case not in held, (
            f"{case} is declared holdout in docs/eval/holdout-manifest.json; "
            "isolation is on by default, so the CI subset silently drops it — "
            "pick a non-holdout case instead"
        )


def test_the_subset_keeps_a_negative_control() -> None:
    """Without one, the `False positives: 0` grep is vacuously true."""
    negatives = [case for case in copied_cases() if is_negative(case)]
    assert negatives, (
        "the CI eval subset has no negative case, so its `False positives: 0` "
        "gate can never fail — a gate that cannot fail is not a gate"
    )


def test_the_subset_keeps_a_positive_case() -> None:
    positives = [case for case in copied_cases() if not is_negative(case)]
    assert positives, "the CI eval subset has no positive case — recall is unmeasurable"


def test_the_step_uses_the_tools_own_gate_with_floors() -> None:
    """`--gate` + explicit floors is what turns a shrunk subset into a failure
    instead of a quieter, smaller pass."""
    source = ci_source()
    step = source[source.index("Evaluate representative golden-case subset"):
                  source.index("Gate: recall must be 100%")]
    assert "--gate" in step, (
        "the eval step no longer passes --gate: a run the tool calls "
        "INSUFFICIENT would pass the grep-only gate"
    )
    assert re.search(r"--min-positive-cases\s+\d+", step), (
        "no explicit positive floor — a subset that shrank to one case would "
        "still be judged"
    )
    assert re.search(r"--min-negative-cases\s+\d+", step), (
        "no explicit negative floor — the vacuous-false-positive case again"
    )
