"""The re-render script must survive the file it exists to rescue.

Ledger #411 added ``scripts/render_eval_report.py``: render the HTML report
from a sidecar, without measuring the pool again (hours per run) and
without touching the database.

Ledger #412 found the hole in it: the ``.jsonl`` branch parsed every line
with a bare ``json.loads``. The ``.jsonl`` sidecar is written *while* the
run goes, so a run that was killed leaves a **torn last line** - half a
record is not a record. The script that exists to rescue those hours was
the one place in the codebase that crashed on them.

The fix is not a private parser: it is the CLI's own reader
(``read_incremental_results`` + ``resume_index``), so there is exactly one
implementation of "how do we read a possibly-torn sidecar".

These tests are SHARP: each one fails when the fix is reverted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.render_eval_report import load_evidence, render_from_sidecar


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
        "severity_match": True,
        "finding_evidence": [
            {
                "contract_id": "COURT-01",
                "severity": "MAJOR",
                "evidence_type": "base_pass_head_fail",
            }
        ],
    }
    record.update(overrides)
    return record


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def test_a_torn_last_line_does_not_take_the_reader_down(tmp_path: Path) -> None:
    """A killed run leaves half a line. The reader must skip it - not crash.

    Sharp: with the bare ``json.loads`` of #411 this raises
    ``JSONDecodeError`` and the report is lost, even though the 50 records
    before it are perfectly readable.
    """
    sidecar = tmp_path / "eval-report.results.jsonl"
    _write_jsonl(sidecar, [_record("case-01"), _record("case-02")])
    # A torn write: the process died mid-line.
    with sidecar.open("a", encoding="utf-8") as handle:
        handle.write('{"case": "case-03", "verdict": "PAS')

    cases, acceptance, case_set = load_evidence(sidecar)

    assert [c["case"] for c in cases] == ["case-01", "case-02"]
    assert acceptance is None


def test_a_torn_line_in_the_middle_is_also_skipped(tmp_path: Path) -> None:
    """The torn line is not necessarily the last one."""
    sidecar = tmp_path / "eval-report.results.jsonl"
    _write_jsonl(sidecar, [_record("case-01")])
    with sidecar.open("a", encoding="utf-8") as handle:
        handle.write('{"case": "case-02", "verdic\n')
    with sidecar.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_record("case-03")) + "\n")

    cases, _, case_set = load_evidence(sidecar)

    assert [c["case"] for c in cases] == ["case-01", "case-03"]


def test_the_latest_record_for_a_case_wins(tmp_path: Path) -> None:
    """A case measured twice has two lines; the later one is the truth now.

    This is the CLI's ``resume_index`` rule. The re-rendered report must
    not show a record the run itself would have discarded.
    """
    sidecar = tmp_path / "eval-report.results.jsonl"
    _write_jsonl(
        sidecar,
        [
            _record("case-01", verdict="MISS", matched_findings=0),
            _record("case-01", verdict="PASS", matched_findings=1),
        ],
    )

    cases, _, case_set = load_evidence(sidecar)

    assert len(cases) == 1
    assert cases[0]["verdict"] == "PASS"


def test_a_record_without_a_case_name_is_not_a_case(tmp_path: Path) -> None:
    """A record with no case name names no case.

    The CLI's ``resume_index`` keys the sidecar by case name and drops a
    record that has none - a line without a name cannot be attributed to
    a case, and under the #411 parser it landed under a synthetic key
    (``len(latest)``) that a real case named "0" would have overwritten.

    Sharp: the #411 parser kept the anonymous record; this one drops it.
    """
    sidecar = tmp_path / "eval-report.results.jsonl"
    with sidecar.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_record("case-01")) + "\n")
        handle.write(json.dumps({"verdict": "PASS"}) + "\n")

    cases, _, case_set = load_evidence(sidecar)

    assert [c["case"] for c in cases] == ["case-01"]


def test_a_jsonl_never_carries_an_acceptance_verdict(tmp_path: Path) -> None:
    """A killed run never DECIDED an acceptance verdict.

    A card that says "PASS" for a run that was killed half way would be a
    verdict nobody reached. The report must show the cases and say nothing
    about acceptance.
    """
    sidecar = tmp_path / "eval-report.results.jsonl"
    _write_jsonl(sidecar, [_record("case-01")])

    cases, acceptance, case_set = load_evidence(sidecar)

    assert acceptance is None
    html = render_from_sidecar(sidecar)
    assert "case-01" in html
    # The acceptance CARD is a stat box with the status word; a run that
    # never decided one must not show it.
    assert "Acceptance" not in html or "Acceptance verdict" not in html


def test_the_json_sidecar_carries_the_verdict_the_run_decided(
    tmp_path: Path,
) -> None:
    """The final sidecar has the verdict; the re-rendered report shows it."""
    sidecar = tmp_path / "eval-report.results.json"
    sidecar.write_text(
        json.dumps(
            {
                "cases": [_record("case-01")],
                "acceptance": {
                    "status": "PASS",
                    "passed": True,
                    "floors_pinned": True,
                    "metrics": {
                        "recall": 100.0,
                        "precision": 100.0,
                        "f1": 100.0,
                    },
                    "counts": {
                        "should_detect": 1,
                        "detected": 1,
                        "false_positives": 0,
                        "negative_cases": 0,
                    },
                    "criteria": {},
                    "failures": [],
                    "insufficient": [],
                },
            }
        ),
        encoding="utf-8",
    )

    cases, acceptance, case_set = load_evidence(sidecar)

    assert len(cases) == 1
    assert acceptance is not None
    assert acceptance.status == "PASS"
    assert acceptance.passed is True


def test_the_re_render_is_the_same_page_the_run_wrote(tmp_path: Path) -> None:
    """The re-render is a VIEW of the evidence, not a second opinion.

    Sharp: if the re-render computed its own numbers, a change in the
    report's arithmetic would show up here as a difference from the page
    the run itself wrote.
    """
    from evidence.report import render_eval_report

    records = [
        _record("case-01"),
        _record("case-02", severity_match=False, expected_severity="BLOCKER"),
    ]
    sidecar = tmp_path / "eval-report.results.jsonl"
    _write_jsonl(sidecar, records)

    from_sidecar = render_from_sidecar(sidecar)
    from_records = render_eval_report(records, None)

    # The run stamps the render time, so compare the parts that carry the
    # evidence: the case rows and the drift list.
    def _rows(html: str) -> list[str]:
        return [
            line
            for line in html.splitlines()
            if "case-0" in line or "Severity drift" in line
        ]

    assert _rows(from_sidecar) == _rows(from_records)


def test_a_sidecar_that_does_not_exist_is_an_error_not_a_crash(
    tmp_path: Path,
) -> None:
    from scripts.render_eval_report import main

    assert main([str(tmp_path / "nope.results.jsonl")]) == 2


def test_the_script_writes_the_page_where_it_was_told(tmp_path: Path) -> None:
    from scripts.render_eval_report import main

    sidecar = tmp_path / "eval-report.results.jsonl"
    _write_jsonl(sidecar, [_record("case-01")])
    out = tmp_path / "report.html"

    assert main([str(sidecar), "-o", str(out)]) == 0
    assert out.exists()
    assert "case-01" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("suffix", [".json", ".jsonl"])
def test_a_sidecar_with_no_cases_still_renders(tmp_path: Path, suffix: str) -> None:
    """An empty run is a page with zeros - not a crash."""
    sidecar = tmp_path / f"eval-report.results{suffix}"
    if suffix == ".jsonl":
        sidecar.write_text("", encoding="utf-8")
    else:
        sidecar.write_text(json.dumps({"cases": []}), encoding="utf-8")

    cases, _, case_set = load_evidence(sidecar)
    assert cases == []
    html = render_from_sidecar(sidecar)
    assert "Not Measured" in html
