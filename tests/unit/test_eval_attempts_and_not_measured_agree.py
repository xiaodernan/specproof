"""--attempts and the "not measured" verdict must not fight each other.

The full-pool run in flight uses --attempts 3, and the NOT_RUN rule
(#399) says: a case whose evidence path could not judge was never
measured. The two must agree in both directions:

- attempt 1 could not judge, attempt 2 DETECTED ⇒ the case WAS measured
  (it was found) ⇒ it must be scored as a detection, NOT as "not
  measured" — otherwise a later attempt's success is thrown away;
- every attempt could not judge ⇒ the case was never measured ⇒
  NOT_RUN, and the reason must survive.

This is the interaction the next full-pool run depends on, so it is
pinned here rather than discovered in a nine-hour run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd


def _write_case(root: Path, name: str) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "spec.md").write_text(
        f"# {name}\n\nThe event must be published exactly once.\n", encoding="utf-8"
    )
    (case_dir / "ground-truth.json").write_text(
        json.dumps({
            "should_detect": True,
            "expected_contract": "EVENT_ONCE-01",
            "expected_severity": "MAJOR",
            "expected_evidence_type": "base_pass_head_fail",
        }),
        encoding="utf-8",
    )
    (case_dir / "scenario.json").write_text(
        json.dumps({"base_ref": "base", "head_ref": "head-v1"}), encoding="utf-8"
    )
    return case_dir


def _unjudgeable() -> dict[str, Any]:
    return {
        "contract_id": "EVENT_ONCE-01",
        "experiment_id": "PROBE-01",
        "verdict": "NON_REPRODUCIBLE",
        "detail": "base artifact does not meet its expected probe profile",
        "severity": "NONE",
        "evidence_type": "probe_differential",
    }


def _detected() -> dict[str, Any]:
    return {
        "contract_id": "EVENT_ONCE-01",
        "experiment_id": "PROBE-01",
        "verdict": "REGRESSION",
        "detail": "probe artifact comparison: head violates payload_timestamp_non_null",
        "severity": "MAJOR",
        "confidence": 0.95,
        "evidence_type": "probe_differential",
    }


class _ScriptedGraph:
    """Runs a scripted sequence of outcomes, one per attempt."""

    def __init__(self, outcomes: list[dict[str, Any]]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        findings: list[dict[str, Any]] = []
        if outcome.get("verdict") == "REGRESSION":
            findings = [{
                "id": "COURT-EVENT_ONCE-01",
                "contract_id": "EVENT_ONCE-01",
                "severity": "MAJOR",
                "confidence": 0.95,
                "evidence_type": "probe_differential",
            }]
        return {
            "confirmed_findings": findings,
            "errors": [],
            "diff_results": [outcome],
            "evidence_pack_saved": False,
            "evidence_pack_error": "not written: this run may not write the audit trail",
        }


def _run(tmp_path: Path, monkeypatch, graph, *, attempts: int) -> tuple[int, str, dict]:
    import agent.graph
    from cli.specproof.commands import eval as eval_module

    monkeypatch.setattr(agent.graph, "build_phase0_graph", lambda: graph)
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir(exist_ok=True)
    (tmp_path / "repo").mkdir(exist_ok=True)
    _write_case(tmp_path / "cases", "case-01-x")
    result = CliRunner().invoke(
        eval_cmd,
        [
            "--cases", str(tmp_path / "cases"),
            "--repo", str(tmp_path / "repo"),
            "--no-llm", "--include-holdout",
            "--attempts", str(attempts),
            "--output", str(tmp_path / "eval-report.html"),
        ],
    )
    data = json.loads(
        (tmp_path / "eval-report.results.json").read_text(encoding="utf-8")
    )
    return result.exit_code, result.output, data["cases"][0]


def test_a_later_attempt_that_detects_wins_over_an_earlier_unjudgeable_one(
    tmp_path, monkeypatch
):
    """Attempt 1 could not judge; attempt 2 found it. The case WAS measured."""
    graph = _ScriptedGraph([_unjudgeable(), _detected()])
    exit_code, output, record = _run(tmp_path, monkeypatch, graph, attempts=3)
    assert exit_code == 0, output
    assert graph.calls == 2, "the second attempt detected it, so it stopped"
    assert record["verdict"] == "PASS", record
    assert record["matched_findings"] == 1
    assert record["attempts"] == 2
    assert record["first_attempt_verdict"] == "NOT_RUN", (
        "the first attempt could not judge, so it was NOT a detection and "
        "not a miss either - it was never compared"
    )


def test_a_case_no_attempt_could_judge_is_not_measured(tmp_path, monkeypatch):
    graph = _ScriptedGraph([_unjudgeable()])
    exit_code, output, record = _run(tmp_path, monkeypatch, graph, attempts=3)
    assert exit_code == 0, output
    assert graph.calls == 3, "it kept trying"
    assert record["verdict"] == "NOT_RUN", record
    assert "could not judge" in record["errors"]
    assert record["attempts"] == 3


def test_the_first_attempt_verdict_says_not_measured_when_it_could_not_judge(
    tmp_path, monkeypatch
):
    """The per-attempt trail must not claim the first attempt was a plain
    MISS: it was never judged."""
    graph = _ScriptedGraph([_unjudgeable()])
    _, _, record = _run(tmp_path, monkeypatch, graph, attempts=2)
    assert record["verdict"] == "NOT_RUN"
    assert record["first_attempt_verdict"] == "NOT_RUN", record
