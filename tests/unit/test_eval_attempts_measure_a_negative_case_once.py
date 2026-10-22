"""A negative case is measured ONCE, and the verdict comes from the attempt
that JUDGED the case.

Two things were wrong in the same loop (ledger #409):

1. A negative case that found NOTHING was not "decisive", so it was
   measured again - up to N times - for a case that was already decided.
   The code, its own comment, ledger #392's design and this file's
   predecessor all said the opposite: a negative case is measured once,
   because a false positive is a hard signal that is reported the moment
   it appears, and hunting for more costs one full measurement per
   negative case. With 35 negatives in the pool that was ~70 wasted full
   measurements per run.

2. The verdict was taken from the LAST attempt, even when that attempt
   had measured nothing (it aborted, or its evidence path could not
   conclude). An attempt that measured nothing must not overwrite what
   an attempt that DID measure said - that is what ledger #399 and #405
   established for a single attempt, and it has to hold across attempts
   too.

The live run that exposed #1 is recorded in the ledger: a negative case
logged "attempt 1: PASS - measuring again".
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd


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


def _finding(contract_id: str = "COURT-01") -> dict:
    return {
        "id": "f-1",
        "contract_id": contract_id,
        "severity": "MAJOR",
        "confidence": 0.9,
        "evidence_type": "DIFFERENTIAL",
    }


def _unjudgeable(contract_id: str = "COURT-01") -> dict:
    return {
        "contract_id": contract_id,
        "experiment_id": "PROBE-01",
        "verdict": "NON_REPRODUCIBLE",
        "detail": "base artifact does not meet its expected probe profile",
        "severity": "NONE",
    }


class _CleanNegative:
    """A negative case: nothing is found, every time."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        return {"confirmed_findings": [], "errors": []}


class _NoisyNegative:
    """A negative case that reports something on the FIRST attempt.

    A false positive is a hard signal and is reported the moment it
    appears - it is not hunted for, and it is not hidden either.
    """

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        return {"confirmed_findings": [_finding()], "errors": []}


class _MissThenUnjudgeable:
    """Attempt 1 judged (and missed); attempt 2 could not conclude."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"confirmed_findings": [], "errors": []}
        return {
            "confirmed_findings": [],
            "errors": [],
            "diff_results": [_unjudgeable()],
        }


class _UnjudgeableThenClean:
    """Attempt 1 could not conclude; attempt 2 judged and found nothing."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {
                "confirmed_findings": [],
                "errors": [],
                "diff_results": [_unjudgeable()],
            }
        return {"confirmed_findings": [], "errors": []}


def _run(tmp_path: Path, monkeypatch, graph, *, attempts: int, should_detect: bool):
    import agent.graph
    from cli.specproof.commands import eval as eval_module

    monkeypatch.setattr(agent.graph, "build_phase0_graph", lambda: graph)
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir(exist_ok=True)
    (tmp_path / "repo").mkdir(exist_ok=True)
    _write_case(tmp_path / "cases", "case-01-x", should_detect=should_detect)
    return CliRunner().invoke(
        eval_cmd,
        [
            "--cases", str(tmp_path / "cases"),
            "--repo", str(tmp_path / "repo"),
            "--no-llm", "--include-holdout",
            "--attempts", str(attempts),
            "--output", str(tmp_path / "eval-report.html"),
        ],
    )


def _record(tmp_path: Path) -> dict:
    data = json.loads(
        (tmp_path / "eval-report.results.json").read_text(encoding="utf-8")
    )
    return data["cases"][0]


# ── a negative case is measured ONCE ───────────────────────────────────────


def test_a_negative_case_that_found_nothing_is_measured_once(tmp_path, monkeypatch):
    """The whole point: it was already decided, so measuring it again is a
    full measurement bought for nothing (ledger #392, #409)."""
    graph = _CleanNegative()
    result = _run(tmp_path, monkeypatch, graph, attempts=3, should_detect=False)
    assert result.exit_code == 0, result.output
    assert graph.calls == 1, "a negative case that found nothing is decided"
    record = _record(tmp_path)
    assert record["verdict"] == "PASS", record
    assert record["attempts"] == 1, record


def test_the_run_does_not_claim_to_measure_a_negative_more_than_once(
    tmp_path, monkeypatch
):
    graph = _CleanNegative()
    result = _run(tmp_path, monkeypatch, graph, attempts=3, should_detect=False)
    assert result.exit_code == 0, result.output
    assert "measuring again" not in result.output
    assert "Cases measured more than once: 0" in result.output


def test_a_negative_case_that_reports_something_is_not_measured_again(
    tmp_path, monkeypatch
):
    """A false positive is a hard signal and is reported the moment it
    appears - it is not hunted for, and it is not hidden either."""
    graph = _NoisyNegative()
    result = _run(tmp_path, monkeypatch, graph, attempts=3, should_detect=False)
    assert result.exit_code == 0, result.output
    assert graph.calls == 1, "the first measurement already decided it"
    record = _record(tmp_path)
    assert record["verdict"] == "FALSE_POSITIVE", record
    assert record["attempts"] == 1, record


# ── the verdict comes from the attempt that JUDGED ─────────────────────────


def test_an_attempt_that_measured_nothing_does_not_overwrite_the_verdict(
    tmp_path, monkeypatch
):
    """Attempt 1 judged (and missed); attempts 2-3 could not conclude. The
    case WAS measured, so it is a MISS - not "never measured"."""
    graph = _MissThenUnjudgeable()
    result = _run(tmp_path, monkeypatch, graph, attempts=3, should_detect=True)
    assert result.exit_code == 0, result.output
    record = _record(tmp_path)
    assert record["verdict"] == "MISS", record
    assert record["attempts"] == 3, "it used every attempt, looking for it"
    assert record["first_attempt_verdict"] == "MISS", record


def test_a_case_whose_first_attempt_could_not_judge_is_measured_again(
    tmp_path, monkeypatch
):
    """An attempt that could not conclude measured nothing, so the case
    gets another turn - and the verdict comes from the one that judged."""
    graph = _UnjudgeableThenClean()
    result = _run(tmp_path, monkeypatch, graph, attempts=3, should_detect=True)
    assert result.exit_code == 0, result.output
    assert graph.calls == 3, "the first attempt judged nothing"
    record = _record(tmp_path)
    assert record["verdict"] == "MISS", record
    assert record["first_attempt_verdict"] == "NOT_RUN", record
