"""Verdict stability classification (§14.1 run_differential).

When the same experiment is repeated, its verdict sequence is classified
as stable (every run agrees), flaky (runs disagree) or contaminated
(environmental state changed between runs — leftover DB/cache state from
an earlier run polluted a later one). A single run is honestly labeled
single_run, never "stable": one observation proves nothing about stability.

A run that executed no tests is not an observation (backlog #532). A
toolchain failure and a selector that matched nothing both return an exit
code without any test having run; deriving ``exit_N`` from that code would
manufacture a verdict out of "nothing was measured". Such a run projects to
the token ``not_run``, and a sequence containing one classifies as
``not_verified`` — contamination still outranks it. Counts are required
evidence: a record without ``test_counts`` reads as zero executed, so
dropping the key cannot buy back a verdict.
"""

from __future__ import annotations


def classify_verdict_sequence(verdicts: list[str]) -> str:
    """Classify a sequence of repeat-run verdicts (same experiment).

    Values are verdict strings (e.g. REGRESSION / COMPLIANT / AMBIGUOUS).
    The classification never guesses: with fewer than two runs the honest
    label is single_run.
    """
    if not verdicts:
        return "no_runs"
    if len(verdicts) == 1:
        return "single_run"
    first = verdicts[0]
    if all(v == first for v in verdicts):
        return "stable"
    return "flaky"


def classify_with_env(verdicts: list[str], env_contaminated: bool) -> str:
    """Stability classification with the environmental-contamination input.

    Contamination takes precedence over agreement: two identical verdicts
    observed on polluted state prove nothing about the experiment.
    """
    if env_contaminated:
        return "contaminated"
    return classify_verdict_sequence(verdicts)


def tests_executed(run: dict[str, object]) -> int:
    """How many tests the run shows it executed; 0 means "cannot be shown".

    Absent or malformed counts are zero on purpose: the summary's job is to
    refuse a verdict it cannot support, and treating "no counts" as "trust
    the exit code" is what let a mute run read as stable before #532.
    """
    counts = run.get("test_counts")
    if not isinstance(counts, dict):
        return 0
    tests = counts.get("tests")
    if isinstance(tests, bool) or not isinstance(tests, int):
        return 0
    return max(tests, 0)


def summarize(
    runs: list[dict[str, object]], contaminated: bool = False,
) -> dict[str, object]:
    """Project repeat-run records onto the stability summary schema.

    runs: list of {"exit_code": int, "error": str, "test_counts": {...}} in
    execution order. A run whose counts show zero executed tests contributes
    the token ``not_run`` and makes the whole sequence ``not_verified``;
    contamination keeps its precedence over every classification.
    """
    verdicts: list[str] = []
    runs_without_execution = 0
    for run in runs:
        if tests_executed(run) == 0:
            verdicts.append("not_run")
            runs_without_execution += 1
        else:
            verdicts.append("exit_" + str(run.get("exit_code")))
    classification = classify_with_env(verdicts, contaminated)
    if runs_without_execution and not contaminated:
        classification = "not_verified"
    return {
        "repeat_count": len(runs),
        "verdicts": verdicts,
        "classification": classification,
        "runs_without_execution": runs_without_execution,
        "runs": runs,
    }
