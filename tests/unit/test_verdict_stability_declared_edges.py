"""#449 — the ``summarize`` projection, which is the module's public surface.

``agent/verdict_stability.py`` is small, and its classifier core is already
pinned by ``test_verdict_stability.py`` (no_runs / single_run / stable /
flaky / contamination precedence). What that test does not pin is
``summarize`` — the projection that turns repeat-run records into the
summary schema embedded into evidence and reports — beyond one happy
"stable" case.

Unpinned here, and now pinned:

* ``contaminated=True`` reaching the projection (and the fact that
  contamination outranks **even** ``no_runs``);
* the single-run projection (honest ``single_run``, never ``stable``);
* the flaky projection and the ``exit_<code>`` verdict tokens it derives;
* an **empty** run list;
* a run record with a **missing ``exit_code``**, which projects to the
  token ``exit_None`` — derived from absent data rather than crashing;
* that the run records are passed through untouched.

#532 changed the projection's input contract: a run must also show how many
tests it executed (``test_counts``), because an ``exit_0`` from a run that
matched no test is not a verdict. The fixtures below therefore carry counts;
the two cases at the end pin the contract itself — zero counts, and counts
missing entirely, both project to ``not_run`` and classify ``not_verified``.
"""
from __future__ import annotations

from typing import Any

from agent.verdict_stability import classify_with_env, summarize


def test_contamination_reaches_the_projection() -> None:
    summary = summarize(
        [
            {"exit_code": 0, "error": "", "test_counts": {"tests": 2}},
            {"exit_code": 0, "error": "", "test_counts": {"tests": 2}},
        ],
        contaminated=True,
    )
    assert summary["classification"] == "contaminated"
    # the verdicts are still projected; only the label changes.
    assert summary["verdicts"] == ["exit_0", "exit_0"]


def test_contamination_outranks_even_no_runs() -> None:
    # No runs at all, but the environment was polluted: the label says so
    # rather than quietly reporting "no runs".
    assert summarize([], contaminated=True)["classification"] == "contaminated"


def test_empty_runs_project_to_no_runs() -> None:
    summary = summarize([])
    assert summary["repeat_count"] == 0
    assert summary["verdicts"] == []
    assert summary["classification"] == "no_runs"
    assert summary["runs"] == []


def test_a_single_run_projects_to_single_run_never_stable() -> None:
    summary = summarize([{"exit_code": 0, "error": "", "test_counts": {"tests": 2}}])
    assert summary["repeat_count"] == 1
    assert summary["verdicts"] == ["exit_0"]
    # one observation proves nothing about stability.
    assert summary["classification"] == "single_run"


def test_disagreeing_runs_project_to_flaky_with_their_tokens() -> None:
    summary = summarize(
        [
            {"exit_code": 0, "error": "", "test_counts": {"tests": 2}},
            {"exit_code": 1, "error": "boom", "test_counts": {"tests": 2}},
        ]
    )
    assert summary["verdicts"] == ["exit_0", "exit_1"]
    assert summary["classification"] == "flaky"
    assert summary["repeat_count"] == 2


def test_a_missing_exit_code_projects_to_the_exit_none_token() -> None:
    # A run record without an exit code does not crash the projection; it
    # yields a token that reads like data but means "absent". Pinned so the
    # derivation is deliberate rather than accidental.
    summary = summarize([{"test_counts": {"tests": 2}}])
    assert summary["verdicts"] == ["exit_None"]
    assert summary["repeat_count"] == 1
    assert summary["classification"] == "single_run"


def test_a_non_int_exit_code_is_stringified_into_the_token() -> None:
    summary = summarize([{"exit_code": "0", "test_counts": {"tests": 1}}])
    assert summary["verdicts"] == ["exit_0"]


def test_the_run_records_are_passed_through_untouched() -> None:
    runs: list[dict[str, Any]] = [
        {"exit_code": 0, "error": "", "mode": "sandbox", "test_counts": {"tests": 1}},
        {"exit_code": 0, "error": "", "mode": "sandbox", "test_counts": {"tests": 1}},
    ]
    summary = summarize(runs)
    assert summary["runs"] is runs
    assert summary["runs"] == runs


def test_a_zero_test_run_projects_to_not_run_never_stable() -> None:
    # #532: the exit code of a run that executed nothing is not a verdict.
    summary = summarize(
        [
            {"exit_code": 0, "error": "", "test_counts": {"tests": 0}},
            {"exit_code": 0, "error": "", "test_counts": {"tests": 0}},
        ]
    )
    assert summary["verdicts"] == ["not_run", "not_run"]
    assert summary["classification"] == "not_verified"
    assert summary["runs_without_execution"] == 2


def test_counts_missing_entirely_are_not_trusted() -> None:
    # Dropping the counts key must not buy back the pre-#532 behaviour.
    summary = summarize(
        [{"exit_code": 0, "error": ""}, {"exit_code": 0, "error": ""}]
    )
    assert summary["verdicts"] == ["not_run", "not_run"]
    assert summary["classification"] == "not_verified"
    assert summary["runs_without_execution"] == 2


def test_one_executed_run_and_one_mute_run_is_not_verified() -> None:
    summary = summarize(
        [
            {"exit_code": 0, "error": "", "test_counts": {"tests": 3}},
            {"exit_code": 1, "error": "build failed", "test_counts": {"tests": 0}},
        ]
    )
    assert summary["verdicts"] == ["exit_0", "not_run"]
    assert summary["classification"] == "not_verified"
    assert summary["runs_without_execution"] == 1


def test_contamination_still_outranks_not_verified() -> None:
    summary = summarize(
        [{"exit_code": 0, "error": "", "test_counts": {"tests": 0}}] * 2,
        contaminated=True,
    )
    assert summary["classification"] == "contaminated"
    assert summary["verdicts"] == ["not_run", "not_run"]


def test_classify_with_env_delegates_when_not_contaminated() -> None:
    # The contamination flag off: every classifier outcome must survive the
    # delegation unchanged, not just the empty case already pinned.
    assert classify_with_env(["A"], False) == "single_run"
    assert classify_with_env(["A", "A"], False) == "stable"
    assert classify_with_env(["A", "B"], False) == "flaky"
