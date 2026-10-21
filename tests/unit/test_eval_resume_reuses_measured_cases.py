"""A killed evaluation must be resumable, not merely survivable.

#377 made the evaluation drop a JSON line per case the moment the case
finishes, so a killed run leaves its measurements behind. That is only
half of the fix: the hours are still gone unless the NEXT run can pick
them up. An 87-case pool at ~700 s a case is ~17 hours of machine time;
re-measuring all of it because the run was killed at hour 16 is not
survivable, it is just expensive.

So the evaluation can RESUME: it reads the sidecar back, re-uses the
records whose inputs are unchanged, and measures only what changed.
The re-used record must be re-used HONESTLY:

- a case whose ground truth changed is measured again, not re-used;
- a record without a fingerprint (written before the fingerprint existed)
  is not re-used, because nobody can prove it measured this case as it
  is now;
- a re-used record is counted exactly like a freshly measured one, so
  the report's metrics cover the WHOLE pool, not just the part this
  run measured.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.specproof.commands.eval import (
    case_fingerprint,
    counter_deltas,
    eval_cmd,
    incremental_results_path,
    read_incremental_results,
    resume_index,
    select_resumable,
)


def _write_case(root: Path, name: str, *, should_detect: bool) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "spec.md").write_text(
        f"# {name}\n\nThe service must reject a null event timestamp.\n",
        encoding="utf-8",
    )
    (case_dir / "ground-truth.json").write_text(
        json.dumps(
            {
                "should_detect": should_detect,
                "expected_contract": "COURT-01",
                "expected_severity": "MAJOR",
                "expected_min_findings": 1,
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "scenario.json").write_text(
        json.dumps({"base_ref": "base", "head_ref": "head-v1"}),
        encoding="utf-8",
    )
    return case_dir


# --- the fingerprint -------------------------------------------------------


def test_the_fingerprint_is_stable_for_the_same_case(tmp_path):
    case_dir = _write_case(tmp_path, "case-01", should_detect=True)
    assert case_fingerprint(case_dir) == case_fingerprint(case_dir)


def test_a_corrected_ground_truth_changes_the_fingerprint(tmp_path):
    """A ground truth that was fixed after the last run makes the old
    measurement STALE - not silently wrong, not silently right."""
    case_dir = _write_case(tmp_path, "case-01", should_detect=True)
    before = case_fingerprint(case_dir)
    (case_dir / "ground-truth.json").write_text(
        json.dumps({"should_detect": True, "expected_contract": "COURT-02"}),
        encoding="utf-8",
    )
    assert case_fingerprint(case_dir) != before


def test_a_case_with_no_scenario_is_not_the_same_case_as_one_with_it(tmp_path):
    case_dir = _write_case(tmp_path, "case-01", should_detect=True)
    before = case_fingerprint(case_dir)
    (case_dir / "scenario.json").unlink()
    assert case_fingerprint(case_dir) != before


# --- choosing what to re-use -----------------------------------------------


def test_a_record_whose_inputs_are_unchanged_is_reused(tmp_path):
    case_dir = _write_case(tmp_path, "case-01", should_detect=True)
    fingerprint = case_fingerprint(case_dir)
    reusable, stale = select_resumable(
        [{"case": "case-01", "fingerprint": fingerprint, "verdict": "PASS"}],
        {"case-01": fingerprint},
    )
    assert "case-01" in reusable
    assert stale == []


def test_a_record_whose_ground_truth_changed_is_not_reused(tmp_path):
    case_dir = _write_case(tmp_path, "case-01", should_detect=True)
    old_fingerprint = case_fingerprint(case_dir)
    (case_dir / "ground-truth.json").write_text(
        json.dumps({"should_detect": False}), encoding="utf-8"
    )
    new_fingerprint = case_fingerprint(case_dir)
    reusable, stale = select_resumable(
        [{"case": "case-01", "fingerprint": old_fingerprint}],
        {"case-01": new_fingerprint},
    )
    assert reusable == {}
    assert stale == ["case-01"]


def test_a_record_without_a_fingerprint_is_not_reused(tmp_path):
    """An older build's record cannot be proven to describe this case as
    it is now, so the case is measured again. 'Probably the same' is how
    a stale number turns into a fresh number."""
    case_dir = _write_case(tmp_path, "case-01", should_detect=True)
    fingerprint = case_fingerprint(case_dir)
    reusable, stale = select_resumable(
        [{"case": "case-01", "verdict": "PASS"}],
        {"case-01": fingerprint},
    )
    assert reusable == {}
    assert stale == ["case-01"]


def test_the_later_record_wins_when_a_case_was_measured_twice():
    records = [
        {"case": "case-01", "verdict": "MISS", "fingerprint": "a"},
        {"case": "case-01", "verdict": "PASS", "fingerprint": "b"},
    ]
    index = resume_index(records)
    assert index["case-01"]["verdict"] == "PASS"


# --- counting a re-used record ---------------------------------------------


def test_a_reused_pass_on_a_positive_case_counts_as_detected():
    assert counter_deltas(
        {"verdict": "PASS", "should_detect": True}
    ) == (1, 1, 0, 0, 0)


def test_a_reused_miss_on_a_positive_case_is_a_denominator_not_a_miss():
    """A case that was measured and missed is still a positive case: it
    belongs in the denominator even when the record is re-used."""
    assert counter_deltas(
        {"verdict": "MISS", "should_detect": True}
    ) == (0, 1, 0, 0, 0)


def test_a_reused_false_positive_counts_as_a_false_positive():
    assert counter_deltas(
        {"verdict": "FALSE_POSITIVE", "should_detect": False}
    ) == (0, 0, 1, 1, 0)


def test_a_reused_not_run_stays_out_of_both_sides_of_the_ratio():
    assert counter_deltas(
        {"verdict": "NOT_RUN", "should_detect": True}
    ) == (0, 0, 0, 0, 1)


# --- the command exposes it ------------------------------------------------


def test_the_eval_command_offers_resume():
    flags = {param.name for param in eval_cmd.params}
    assert "resume" in flags


# --- end to end: a second run measures nothing twice ------------------------


class _FakeGraph:
    """A pipeline that finds the defect in case-01 and nothing elsewhere."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def invoke(self, state: dict) -> dict:
        self.calls.append(str(state.get("spec_path", "")))
        if "case-01" in str(state.get("spec_path", "")):
            return {
                "confirmed_findings": [
                    {
                        "id": "f-1",
                        "contract_id": "COURT-01",
                        "severity": "MAJOR",
                        "confidence": 0.9,
                        "evidence_type": "DIFFERENTIAL",
                    }
                ],
                "errors": [],
            }
        return {"confirmed_findings": [], "errors": []}


def _run_eval(tmp_path, monkeypatch, calls, *, resume: bool):
    """Invoke the eval command against a two-case pool with a fake pipeline."""
    from click.testing import CliRunner

    import agent.graph
    from cli.specproof.commands import eval as eval_module

    monkeypatch.setattr(
        agent.graph, "build_phase0_graph", lambda: _FakeGraph(calls)
    )
    # The MySQL probe must not reach a database from a unit test.
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    args = [
        "--cases", str(tmp_path / "cases"),
        "--repo", str(tmp_path / "repo"),
        "--no-llm",
        "--include-holdout",
        "--output", str(tmp_path / "eval-report.html"),
    ]
    if resume:
        args.append("--resume")
    return CliRunner().invoke(eval_cmd, args)


def _sidecar(tmp_path) -> dict:
    return json.loads(
        (tmp_path / "eval-report.results.json").read_text(encoding="utf-8")
    )


def test_a_resumed_run_does_not_measure_what_it_already_measured(tmp_path, monkeypatch):
    (tmp_path / "cases").mkdir()
    (tmp_path / "repo").mkdir()
    _write_case(tmp_path / "cases", "case-01", should_detect=True)
    _write_case(tmp_path / "cases", "case-02", should_detect=False)

    calls: list[str] = []
    first = _run_eval(tmp_path, monkeypatch, calls, resume=False)
    assert first.exit_code == 0, first.output
    assert len(calls) == 2, "the first run measures the whole pool"

    resumed_calls: list[str] = []
    second = _run_eval(tmp_path, monkeypatch, resumed_calls, resume=True)
    assert second.exit_code == 0, second.output
    assert resumed_calls == [], "the second run must not re-measure anything"

    sidecar = _sidecar(tmp_path)
    assert sidecar["resumed_cases"] == 2
    assert sidecar["total_cases"] == 2
    # The metrics of a resumed run cover the WHOLE pool, not the part
    # this run happened to measure.
    assert sidecar["recall"] == 100.0
    assert sidecar["precision"] == 100.0
    assert sidecar["negative_cases"] == 1
    assert sidecar["should_detect"] == 1
    assert sidecar["detected"] == 1


def test_a_resumed_run_remeasures_a_case_whose_ground_truth_changed(tmp_path, monkeypatch):
    (tmp_path / "cases").mkdir()
    (tmp_path / "repo").mkdir()
    _write_case(tmp_path / "cases", "case-01", should_detect=True)
    _write_case(tmp_path / "cases", "case-02", should_detect=False)

    calls: list[str] = []
    assert _run_eval(tmp_path, monkeypatch, calls, resume=False).exit_code == 0
    assert len(calls) == 2

    # The ground truth of case-01 is corrected: the case is a negative one
    # now, so the old record (a positive case that was detected) is stale.
    (tmp_path / "cases" / "case-01" / "ground-truth.json").write_text(
        json.dumps({"should_detect": False, "expected_contract": "COURT-01"}),
        encoding="utf-8",
    )

    resumed_calls: list[str] = []
    assert _run_eval(tmp_path, monkeypatch, resumed_calls, resume=True).exit_code == 0
    assert len(resumed_calls) == 1, "only the changed case is measured again"
    assert "case-01" in resumed_calls[0]

    sidecar = _sidecar(tmp_path)
    assert sidecar["resumed_cases"] == 1
    assert sidecar["should_detect"] == 0
    assert sidecar["negative_cases"] == 2
    # The false positive the stale record would have hidden is now counted.
    assert sidecar["false_positives"] == 1


def test_the_sidecar_keeps_both_the_old_and_the_new_record_of_a_case(tmp_path, monkeypatch):
    """The sidecar is an audit trail: a case measured twice has two lines,
    and the later one is the one that describes the case as it is now."""
    (tmp_path / "cases").mkdir()
    (tmp_path / "repo").mkdir()
    _write_case(tmp_path / "cases", "case-01", should_detect=True)

    calls: list[str] = []
    assert _run_eval(tmp_path, monkeypatch, calls, resume=False).exit_code == 0
    (tmp_path / "cases" / "case-01" / "ground-truth.json").write_text(
        json.dumps({"should_detect": False}), encoding="utf-8"
    )
    assert _run_eval(tmp_path, monkeypatch, calls, resume=True).exit_code == 0

    records = read_incremental_results(
        incremental_results_path(tmp_path / "eval-report.html")
    )
    assert len(records) == 2
    assert [r["case"] for r in records] == ["case-01", "case-01"]
    assert resume_index(records)["case-01"]["should_detect"] is False
