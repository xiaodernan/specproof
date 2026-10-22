"""The first-try recall must be a number about the WHOLE pool, and it must
not count a run that never ran as a run that missed.

Two defects, both in the same counter (ledger #410):

1. **A re-used record contributed nothing to the first-try counters.**
   ``counter_deltas`` (the function that says what one record is worth
   to the run) covered the run counters but not the first-try ones, so
   on a RESUMED run the first-try recall was computed over the handful
   of cases that run measured fresh - and the reader could not tell. A
   resumed run of an 87-case pool would print "First-try recall: 2/2"
   about the 2 cases it re-measured, which reads like the pool's number.

2. **A first attempt that could not judge counted as a first-try
   MISS.** The tool never looked, so it neither found nor missed the
   defect; counting it in the denominator says "the tool failed on the
   first try" about a run that never ran (ledger #399, #405). It is
   excluded - and the number of excluded cases is reported next to the
   ratio, so the exclusion hides nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd, first_try_deltas

# ── the pure rule ─────────────────────────────────────────────────────────


def test_a_positive_case_found_on_the_first_attempt_counts() -> None:
    assert first_try_deltas("PASS", True, "PASS") == (1, 1, 0)


def test_a_positive_case_missed_on_the_first_attempt_is_a_denominator() -> None:
    assert first_try_deltas("PASS", True, "MISS") == (0, 1, 0)


def test_a_first_attempt_that_could_not_judge_is_excluded() -> None:
    """It never compared anything, so it is neither found nor missed."""
    assert first_try_deltas("PASS", True, "NOT_RUN") == (0, 0, 1)


def test_a_record_without_a_first_attempt_verdict_is_excluded() -> None:
    """An older record may not carry the field at all; that is "unknown",
    not "missed"."""
    assert first_try_deltas("PASS", True, "") == (0, 0, 1)


def test_a_negative_case_contributes_nothing() -> None:
    assert first_try_deltas("PASS", False, "PASS") == (0, 0, 0)


def test_a_case_that_was_never_measured_contributes_nothing() -> None:
    assert first_try_deltas("NOT_RUN", True, "NOT_RUN") == (0, 0, 0)


# ── end to end ─────────────────────────────────────────────────────────────


def _write_case(root: Path, name: str, *, should_detect: bool) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "spec.md").write_text(
        f"# {name}\n\nThe service must reject a null event timestamp.\n",
        encoding="utf-8",
    )
    (case_dir / "ground-truth.json").write_text(
        json.dumps({
            "should_detect": should_detect,
            "expected_contract": "COURT-01",
            "expected_severity": "MAJOR",
            "expected_min_findings": 1,
        }),
        encoding="utf-8",
    )
    (case_dir / "scenario.json").write_text(
        json.dumps({"base_ref": "base", "head_ref": "head-v1"}),
        encoding="utf-8",
    )
    return case_dir


def _finding() -> dict:
    return {
        "id": "f-1",
        "contract_id": "COURT-01",
        "severity": "MAJOR",
        "confidence": 0.9,
        "evidence_type": "DIFFERENTIAL",
    }


class _PoolGraph:
    """case-a is detected; case-b is never detected."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def invoke(self, state: dict) -> dict:
        spec = str(state.get("spec_path", ""))
        self.calls.append(spec)
        if "case-a" in spec:
            return {"confirmed_findings": [_finding()], "errors": []}
        return {"confirmed_findings": [], "errors": []}


def _run(tmp_path: Path, monkeypatch, calls, *, resume: bool):
    import agent.graph
    from cli.specproof.commands import eval as eval_module

    monkeypatch.setattr(
        agent.graph, "build_phase0_graph", lambda: _PoolGraph(calls)
    )
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir(exist_ok=True)
    (tmp_path / "repo").mkdir(exist_ok=True)
    _write_case(tmp_path / "cases", "case-a", should_detect=True)
    _write_case(tmp_path / "cases", "case-b", should_detect=True)
    args = [
        "--cases", str(tmp_path / "cases"),
        "--repo", str(tmp_path / "repo"),
        "--no-llm", "--include-holdout",
        "--attempts", "2",
        "--output", str(tmp_path / "eval-report.html"),
    ]
    if resume:
        args.append("--resume")
    return CliRunner().invoke(eval_cmd, args)


def test_a_resumed_run_reports_the_first_try_recall_of_the_whole_pool(
    tmp_path, monkeypatch
):
    """The re-used cases ARE part of the pool, so their first attempts are
    part of the number. Before the fix the resumed run counted only the
    cases it measured fresh."""
    calls: list[str] = []
    first = _run(tmp_path, monkeypatch, calls, resume=False)
    assert first.exit_code == 0, first.output
    assert "First-try recall:   50.0% (1/2 positive cases" in first.output

    calls.clear()
    second = _run(tmp_path, monkeypatch, calls, resume=True)
    assert second.exit_code == 0, second.output
    assert calls == [], "nothing was measured again"
    assert "First-try recall:   50.0% (1/2 positive cases" in second.output, (
        "the re-used cases must be in the number too - they are the pool"
    )


def test_the_number_of_excluded_cases_is_reported_next_to_the_ratio(
    tmp_path, monkeypatch
):
    """A first attempt that could not judge is excluded from the
    denominator - and the exclusion is stated, not silent."""
    class _FirstAttemptBlind:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, state: dict) -> dict:
            self.calls += 1
            if self.calls == 1:
                return {
                    "confirmed_findings": [],
                    "errors": [],
                    "diff_results": [{
                        "contract_id": "COURT-01",
                        "experiment_id": "PROBE-01",
                        "verdict": "NON_REPRODUCIBLE",
                        "detail": "base artifact does not meet its expected probe profile",
                        "severity": "NONE",
                    }],
                }
            return {"confirmed_findings": [_finding()], "errors": []}

    import agent.graph
    from cli.specproof.commands import eval as eval_module

    monkeypatch.setattr(
        agent.graph, "build_phase0_graph", lambda: _FirstAttemptBlind()
    )
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir(exist_ok=True)
    (tmp_path / "repo").mkdir(exist_ok=True)
    _write_case(tmp_path / "cases", "case-a", should_detect=True)
    result = CliRunner().invoke(
        eval_cmd,
        [
            "--cases", str(tmp_path / "cases"),
            "--repo", str(tmp_path / "repo"),
            "--no-llm", "--include-holdout",
            "--attempts", "2",
            "--output", str(tmp_path / "eval-report.html"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "First-try recall:" in result.output
    assert "excluded from that number: 1 positive case(s)" in result.output, (
        result.output
    )
