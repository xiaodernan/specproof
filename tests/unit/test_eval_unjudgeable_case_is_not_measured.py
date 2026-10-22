"""A case the evidence could not JUDGE is not measured — it is not a miss.

Ledger #397 measured it: the pool's "51/52" contained a case whose probe
came back NON_REPRODUCIBLE (the base side's probe test had failed, so the
base's artifact was empty, so the probe could not compare base against
head). The pipeline said "I looked and could not decide"; the evaluator
scored it MISS, which says "the tool failed to detect the defect" about a
run that never compared anything.

The repository already says that is wrong — the NOT_RUN branch exists for
exactly this ("Scoring that as a MISS would say 'the tool failed to detect
the defect' about a run that never looked"). This makes the second source
of "never looked" reach it: an evidence path that could not judge.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.specproof.commands.eval import (
    eval_cmd,
    unjudgeable_reason,
)


def _unjudgeable(contract_id: str = "COURT-01", experiment: str = "PROBE-01") -> dict:
    return {
        "contract_id": contract_id,
        "experiment_id": experiment,
        "verdict": "NON_REPRODUCIBLE",
        "detail": "base artifact does not meet its expected probe profile",
        "severity": "NONE",
    }


# ── the pure rule ────────────────────────────────────────────────────────


def test_a_judgeable_case_has_no_reason() -> None:
    assert unjudgeable_reason([], "COURT-01") == ""
    assert unjudgeable_reason(
        [{"contract_id": "COURT-01", "verdict": "REGRESSION"}], "COURT-01"
    ) == ""


def test_an_unjudgeable_probe_for_this_contract_is_reported() -> None:
    reason = unjudgeable_reason([_unjudgeable()], "COURT-01")
    assert "PROBE-01" in reason
    assert "COURT-01" in reason
    assert "could not judge" in reason


def test_an_unjudgeable_whole_run_is_reported() -> None:
    """The differential's whole-run entry carries the placeholder contract
    id, and it means the comparison for this case never happened."""
    reason = unjudgeable_reason([_unjudgeable("DIFF-01", "DIFF-01")], "COURT-01")
    assert reason != ""
    assert "DIFF-01" in reason


def test_another_contract_s_unjudgeable_entry_says_nothing() -> None:
    """A different contract's unjudgeable evidence is not this case's."""
    assert unjudgeable_reason([_unjudgeable("CACHE-01")], "COURT-01") == ""


def test_the_reason_carries_the_detail_so_the_reader_can_act() -> None:
    reason = unjudgeable_reason([_unjudgeable()], "COURT-01")
    assert "base artifact does not meet" in reason


# ── end to end through the evaluator ──────────────────────────────────────


def _write_case(root: Path, name: str, *, should_detect: bool) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "spec.md").write_text(
        f"# {name}\n\nThe event must be published exactly once.\n", encoding="utf-8"
    )
    (case_dir / "ground-truth.json").write_text(
        json.dumps({
            "should_detect": should_detect,
            "expected_contract": "COURT-01",
            "expected_severity": "MAJOR",
            "expected_evidence_type": "base_pass_head_fail",
        }),
        encoding="utf-8",
    )
    (case_dir / "scenario.json").write_text(
        json.dumps({"base_ref": "base", "head_ref": "head-v1"}), encoding="utf-8"
    )
    return case_dir


class _Graph:
    """A pipeline that found nothing and could not judge the case."""

    def __init__(self, diff_results: list[dict]) -> None:
        self.diff_results = diff_results

    def invoke(self, state: dict) -> dict:
        return {
            "confirmed_findings": [],
            "errors": [],
            "diff_results": self.diff_results,
            "evidence_pack_saved": False,
            "evidence_pack_error": "not written: this run may not write the audit trail",
        }


def _run(tmp_path: Path, monkeypatch, graph) -> tuple[int, str]:
    import agent.graph
    from cli.specproof.commands import eval as eval_module

    monkeypatch.setattr(agent.graph, "build_phase0_graph", lambda: graph)
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir(exist_ok=True)
    (tmp_path / "repo").mkdir(exist_ok=True)
    _write_case(tmp_path / "cases", "case-01-unjudgeable", should_detect=True)
    result = CliRunner().invoke(
        eval_cmd,
        [
            "--cases", str(tmp_path / "cases"),
            "--repo", str(tmp_path / "repo"),
            "--no-llm", "--include-holdout",
            "--output", str(tmp_path / "eval-report.html"),
        ],
    )
    return result.exit_code, result.output


def _record(tmp_path: Path) -> dict:
    data = json.loads(
        (tmp_path / "eval-report.results.json").read_text(encoding="utf-8")
    )
    return data["cases"][0]


def test_a_case_the_evidence_could_not_judge_is_not_a_miss(tmp_path, monkeypatch):
    """The whole point: it was never measured, so it must not be scored
    as "the tool failed to detect the defect"."""
    exit_code, output = _run(
        tmp_path, monkeypatch, _Graph([_unjudgeable()])
    )
    assert exit_code == 0, output
    record = _record(tmp_path)
    assert record["verdict"] == "NOT_RUN", record
    assert "could not judge" in record["errors"]
    assert "NOT RUN:" in output


def test_the_not_measured_case_is_out_of_the_recall_denominator(tmp_path, monkeypatch):
    """A NOT_RUN case is excluded from both sides of the ratio, so the
    recall is not dragged down by a case nobody measured — and the
    sample-size floor still sees that the sample got smaller."""
    exit_code, output = _run(
        tmp_path, monkeypatch, _Graph([_unjudgeable()])
    )
    assert exit_code == 0, output
    data = json.loads(
        (tmp_path / "eval-report.results.json").read_text(encoding="utf-8")
    )
    assert data["not_run"] == 1
    assert data["should_detect"] == 0, "an unmeasured case is not a positive"
    assert "Not run:            1" in output


def test_a_case_with_a_finding_is_still_scored(tmp_path, monkeypatch):
    """The rule only applies when NOTHING was found: a case that found
    the defect was measured, whatever else the evidence path said."""
    class _Found(_Graph):
        def invoke(self, state: dict) -> dict:
            out = super().invoke(state)
            out["confirmed_findings"] = [{
                "id": "COURT-COURT-01",
                "contract_id": "COURT-01",
                "severity": "MAJOR",
                "confidence": 0.9,
                "evidence_type": "base_pass_head_fail",
            }]
            return out

    exit_code, output = _run(tmp_path, monkeypatch, _Found([_unjudgeable()]))
    assert exit_code == 0, output
    record = _record(tmp_path)
    assert record["verdict"] == "PASS", record
    assert record["matched_findings"] == 1
