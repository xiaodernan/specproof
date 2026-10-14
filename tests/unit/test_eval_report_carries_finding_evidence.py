"""A severity mismatch must be diagnosable from the eval report alone.

`case-17` measured MAJOR where the golden expects BLOCKER. The report said so
but not *why*: the per-case record dropped the finding's own evidence, so a
reader could not tell "the differential captured a consistent DB" (its effect
was rolled back / never persisted) from "no DB dump was available at all"
(capture failed) -- two verdicts with completely different fixes. It also hid
the differential's confidence.

The record now carries `finding_evidence`: the evidence fields the finding
already set (contract_id, severity, confidence, evidence_type,
db_state_verdict), copied verbatim -- no new claims.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd


def _make_case(root: Path, name: str, *, ground_truth: dict[str, Any]) -> Path:
    case = root / "cases" / name
    case.mkdir(parents=True)
    (case / "spec.md").write_text("# Case\n\nMust do it.\n", encoding="utf-8")
    (case / "ground-truth.json").write_text(json.dumps(ground_truth), encoding="utf-8")
    (case / "scenario.json").write_text(
        json.dumps({"base_ref": "base", "head_ref": "head-v1"}), encoding="utf-8"
    )
    return case


def _invoke(root: Path, repo: Path, monkeypatch: Any, final: dict[str, Any]) -> Any:
    class _Graph:
        def invoke(self, _state: dict[str, Any]) -> dict[str, Any]:
            return final

    monkeypatch.setattr("agent.graph.build_phase0_graph", lambda: _Graph())
    return CliRunner().invoke(
        eval_cmd,
        ["--cases", str(root / "cases"), "--repo", str(repo),
         "--output", str(root / "report.html")],
        catch_exceptions=False,
    )


def _sidecar_case(root: Path, index: int = 0) -> dict[str, Any]:
    data = json.loads((root / "report.results.json").read_text(encoding="utf-8"))
    return data["cases"][index]


def test_a_severity_mismatch_carries_the_findings_evidence(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _make_case(
        tmp_path, "case-x",
        ground_truth={
            "should_detect": True,
            "expected_contract": "UNIQUE-01",
            "expected_severity": "BLOCKER",
        },
    )
    finding = {
        "contract_id": "UNIQUE-01",
        "severity": "MAJOR",
        "confidence": 0.88,
        "evidence_type": "base_pass_head_fail",
        "db_state_verdict": "DB_CONSISTENT",
    }

    result = _invoke(tmp_path, not_a_repo, monkeypatch, {"confirmed_findings": [finding]})

    assert result.exit_code == 0, result.output
    record = _sidecar_case(tmp_path)
    assert record["matched_severities"] == "MAJOR"
    assert record["expected_severity"] == "BLOCKER"
    evidence = record["finding_evidence"]
    assert evidence, record
    assert evidence[0]["db_state_verdict"] == "DB_CONSISTENT", evidence
    assert evidence[0]["confidence"] == 0.88, evidence
    assert evidence[0]["contract_id"] == "UNIQUE-01", evidence


def test_a_miss_still_carries_evidence_so_it_is_diagnosable(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    """When nothing matches, fall back to every finding: a MISS must be
    diagnosable too, not blank."""
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _make_case(
        tmp_path, "case-y",
        ground_truth={"should_detect": True, "expected_contract": "AUTH-01"},
    )
    finding = {"contract_id": "SOMETHING-ELSE", "severity": "MINOR"}

    result = _invoke(tmp_path, not_a_repo, monkeypatch, {"confirmed_findings": [finding]})

    assert result.exit_code == 0, result.output
    record = _sidecar_case(tmp_path)
    assert record["verdict"] == "MISS"
    assert record["finding_evidence"] == [
        {"contract_id": "SOMETHING-ELSE", "severity": "MINOR"}
    ]


def test_a_not_run_case_has_empty_finding_evidence(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _make_case(
        tmp_path, "case-z",
        ground_truth={"should_detect": True, "expected_contract": "AUTH-01"},
    )

    result = _invoke(tmp_path, not_a_repo, monkeypatch, {"errors": ["boom"]})

    assert result.exit_code == 0, result.output
    record = _sidecar_case(tmp_path)
    assert record["verdict"] == "NOT_RUN"
    assert record["finding_evidence"] == []
