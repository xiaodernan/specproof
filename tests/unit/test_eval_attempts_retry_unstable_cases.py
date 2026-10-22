"""A case whose detection is unstable must not decide the pool by luck.

Ledger #391 measured it: the same case, the same code, two runs — one
found the defect, one did not. A pool number that depends on that is a
number that changes with the weather.

So the evaluation can measure a case more than once (``--attempts N``):

- a POSITIVE case is measured again until it is detected, so the recall
  that gets reported answers "CAN this defect be found";
- "was it found the FIRST time" is recorded per case and reported
  separately, so the instability is visible instead of hidden;
- a NEGATIVE case is still measured once: a false positive is a hard
  signal and is reported the moment it appears, and hunting for more
  would cost one full measurement per negative case.

These tests pin that behaviour with a fake pipeline that misses first
and detects on the second attempt.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.specproof.commands.eval import (
    eval_cmd,
    matched_findings,
    verdict_for,
)


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


class _FlakyGraph:
    """Misses the first attempt, detects on the second."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"confirmed_findings": [], "errors": []}
        return {"confirmed_findings": [_finding()], "errors": []}


class _StableGraph:
    """Detects on the first attempt, every time."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        return {"confirmed_findings": [_finding()], "errors": []}


def _run(tmp_path: Path, monkeypatch, graph, *, attempts: int):
    import agent.graph
    from cli.specproof.commands import eval as eval_module

    monkeypatch.setattr(agent.graph, "build_phase0_graph", lambda: graph)
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir(exist_ok=True)
    (tmp_path / "repo").mkdir(exist_ok=True)
    _write_case(tmp_path / "cases", "case-01-flaky", should_detect=True)
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


def _sidecar(tmp_path: Path) -> dict:
    return json.loads(
        (tmp_path / "eval-report.results.json").read_text(encoding="utf-8")
    )


# ── the pure rules ────────────────────────────────────────────────────────


def test_a_matching_finding_is_the_one_the_case_asked_for() -> None:
    matched = matched_findings([_finding()], "COURT-01", "base_pass_head_fail")
    assert len(matched) == 1


def test_a_finding_with_another_contract_is_not_a_match() -> None:
    matched = matched_findings([_finding("CACHE-01")], "COURT-01", "base_pass_head_fail")
    assert matched == []


def test_a_positive_case_with_a_match_passes() -> None:
    verdict = verdict_for(True, [_finding()], [_finding()], 1)
    assert verdict == "PASS"


def test_a_positive_case_without_a_match_misses() -> None:
    verdict = verdict_for(True, [], [], 1)
    assert verdict == "MISS"


def test_a_negative_case_with_any_finding_is_a_false_positive() -> None:
    verdict = verdict_for(False, [_finding()], [], 1)
    assert verdict == "FALSE_POSITIVE"


def test_a_negative_case_without_findings_passes() -> None:
    verdict = verdict_for(False, [], [], 1)
    assert verdict == "PASS"


# ── the loop ──────────────────────────────────────────────────────────────


def test_an_unstable_case_is_measured_again_until_it_is_detected(tmp_path, monkeypatch):
    """The pool's number must not depend on the first attempt's luck."""
    graph = _FlakyGraph()
    result = _run(tmp_path, monkeypatch, graph, attempts=3)
    assert result.exit_code == 0, result.output
    assert graph.calls == 2, "the second attempt detected it, so it stopped"
    record = _sidecar(tmp_path)["cases"][0]
    assert record["verdict"] == "PASS", "the defect CAN be found"
    assert record["attempts"] == 2
    assert record["first_attempt_verdict"] == "MISS", "the first attempt missed it"


def test_the_first_try_numbers_are_reported_next_to_the_headline(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, _FlakyGraph(), attempts=3)
    assert result.exit_code == 0, result.output
    assert "First-try recall:" in result.output
    assert "unstable detection: case-01-flaky needed 2 attempts" in result.output


def test_a_stable_case_is_still_measured_once(tmp_path, monkeypatch):
    """The extra attempts must not cost anything on a pool that is stable."""
    graph = _StableGraph()
    result = _run(tmp_path, monkeypatch, graph, attempts=3)
    assert result.exit_code == 0, result.output
    assert graph.calls == 1, "a detection on the first attempt is decisive"
    record = _sidecar(tmp_path)["cases"][0]
    assert record["verdict"] == "PASS"
    assert record["attempts"] == 1
    assert record["first_attempt_verdict"] == "PASS"


def test_one_attempt_means_one_measurement(tmp_path, monkeypatch):
    """The default is unchanged: one attempt, and the miss is reported as a
    miss (the honest number when nobody asked for a retry)."""
    graph = _FlakyGraph()
    result = _run(tmp_path, monkeypatch, graph, attempts=1)
    assert result.exit_code == 0, result.output
    assert graph.calls == 1
    record = _sidecar(tmp_path)["cases"][0]
    assert record["verdict"] == "MISS"
    assert record["attempts"] == 1
