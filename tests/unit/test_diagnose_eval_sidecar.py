"""The sidecar must be readable on its own - the diagnosis must not need
another run.

The full-pool evaluation takes hours. The questions asked afterwards are
always the same: which cases were never measured, WHICH side failed and
what that side printed, which cases were measured more than once and
why, and which cases drifted in severity.

``scripts/diagnose_eval_sidecar.py`` answers all of that from the
sidecar alone - no measurement, no database, no re-run. The ledger's
queue asks for exactly this ("use that run's sidecar to find out why
the base side failed, then fix it").

These tests are SHARP: they fail if the tool stops reporting a case,
stops naming a side, or stops quoting that side's output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "diagnose_eval_sidecar.py"


def _record(case: str, **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": case,
        "verdict": "PASS",
        "should_detect": True,
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 1,
        "matched_severities": "MAJOR",
        "contract_level": "MAJOR",
        "all_matched_severities": "MAJOR",
        "contracts_found": "COURT-01",
        "attempts": 1,
        "first_attempt_verdict": "PASS",
        "finding_evidence": [
            {
                "contract_id": "COURT-01",
                "severity": "MAJOR",
                "evidence_type": "base_pass_head_fail",
                "db_state_verdict": "DB_CONSISTENT",
            }
        ],
    }
    record.update(overrides)
    return record


def _run(tmp_path: Path, records: list[dict[str, Any]], *, as_json: bool = False):
    if as_json:
        sidecar = tmp_path / "eval-report.results.json"
        sidecar.write_text(
            json.dumps({"cases": records}), encoding="utf-8"
        )
    else:
        sidecar = tmp_path / "eval-report.results.jsonl"
        sidecar.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
        )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(sidecar)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    return result


def test_the_tool_reads_a_jsonl_sidecar(tmp_path: Path) -> None:
    result = _run(tmp_path, [_record("case-01")])
    assert result.returncode == 0, result.stderr
    assert "case-01" not in result.stdout  # a healthy case is not listed
    assert "every case was measured" in result.stdout
    assert "cases            : 1" in result.stdout


def test_the_tool_reads_a_json_sidecar(tmp_path: Path) -> None:
    result = _run(tmp_path, [_record("case-01")], as_json=True)
    assert result.returncode == 0, result.stderr
    assert "cases            : 1" in result.stdout


def test_a_case_that_was_never_measured_is_named_with_its_reason(
    tmp_path: Path,
) -> None:
    record = _record(
        "case-99",
        verdict="NOT_RUN",
        matched_findings=0,
        matched_severities="—",
        contract_level="",
        contracts_found="",
        finding_evidence=[],
        errors="the evidence path could not judge this case",
    )
    result = _run(tmp_path, [_record("case-01"), record])
    assert "NOT MEASURED (1)" in result.stdout
    assert "case-99" in result.stdout
    assert "the evidence path could not judge this case" in result.stdout
    # and the exit code says something is wrong
    assert result.returncode == 1


def test_the_failing_side_s_output_is_quoted(tmp_path: Path) -> None:
    """The DIAGNOSIS: the side that failed and its own output."""
    record = _record(
        "case-99",
        verdict="NOT_RUN",
        matched_findings=0,
        errors="the evidence path could not judge this case",
        finding_evidence=[],
        base_output="Tests run: 1, Failures: 1\njava.lang.AssertionError: expected 2 but was 1",
    )
    result = _run(tmp_path, [record])
    assert "base output" in result.stdout
    assert "java.lang.AssertionError" in result.stdout


def test_the_head_side_s_output_is_quoted_too(tmp_path: Path) -> None:
    record = _record(
        "case-99",
        verdict="NOT_RUN",
        matched_findings=0,
        errors="the evidence path could not judge this case",
        finding_evidence=[],
        head_output="COMPILATION ERROR: cannot find symbol",
    )
    result = _run(tmp_path, [record])
    assert "head output" in result.stdout
    assert "COMPILATION ERROR" in result.stdout


def test_a_retried_case_is_named_with_its_reason(tmp_path: Path) -> None:
    record = _record(
        "case-74", attempts=2, first_attempt_verdict="MISS",
    )
    result = _run(tmp_path, [record])
    assert "MEASURED MORE THAN ONCE (1)" in result.stdout
    assert "case-74" in result.stdout
    assert "unstable detection" in result.stdout


def test_a_consistently_missed_case_says_so(tmp_path: Path) -> None:
    record = _record(
        "case-75",
        verdict="MISS",
        attempts=3,
        first_attempt_verdict="MISS",
        matched_findings=0,
        contract_level="",
        contracts_found="",
        finding_evidence=[],
    )
    result = _run(tmp_path, [record])
    assert "consistently missed" in result.stdout


def test_a_severity_drift_is_named_with_its_evidence_and_db_state(
    tmp_path: Path,
) -> None:
    record = _record(
        "case-17",
        expected_severity="BLOCKER",
        matched_severities="MAJOR",
        contract_level="MAJOR",
        all_matched_severities="MAJOR",
    )
    result = _run(tmp_path, [record])
    assert "SEVERITY DRIFT" in result.stdout
    assert "case-17" in result.stdout
    assert "expected BLOCKER, got MAJOR" in result.stdout
    assert "DB_CONSISTENT" in result.stdout
    assert "base_pass_head_fail" in result.stdout


def test_a_torn_last_line_does_not_stop_the_diagnosis(tmp_path: Path) -> None:
    """A killed run leaves half a line - the diagnosis must still work."""
    sidecar = tmp_path / "eval-report.results.jsonl"
    sidecar.write_text(
        json.dumps(_record("case-01")) + "\n" + '{"case": "case-02", "verd',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(sidecar)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert "cases            : 1" in result.stdout


def test_a_missing_sidecar_is_an_error_not_a_crash(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.results.jsonl")],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 2
    assert "no such sidecar" in result.stderr
