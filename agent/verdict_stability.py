"""Verdict stability classification (§14.1 run_differential).

When the same experiment is repeated, its verdict sequence is classified
as stable (every run agrees), flaky (runs disagree) or contaminated
(environmental state changed between runs — leftover DB/cache state from
an earlier run polluted a later one). A single run is honestly labeled
single_run, never "stable": one observation proves nothing about stability.
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


def summarize(
    runs: list[dict[str, object]], contaminated: bool = False,
) -> dict[str, object]:
    """Project repeat-run records onto the stability summary schema.

    runs: list of {"exit_code": int, "error": str} in execution order.
    """
    verdicts = ["exit_" + str(r.get("exit_code")) for r in runs]
    return {
        "repeat_count": len(runs),
        "verdicts": verdicts,
        "classification": classify_with_env(verdicts, contaminated),
        "runs": runs,
    }
