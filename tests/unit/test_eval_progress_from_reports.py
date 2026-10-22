"""The progress read must agree with the evaluation's own verdicts.

`scripts/eval_progress_from_reports.py` reads the per-case reports a
running evaluation leaves behind and classifies each case by the
evaluation's own rule. A derived number is only worth reading if it
matches the real one, so these tests pin the rule against hand-written
reports: the same case, the same report, the same verdict the
evaluation would have written.
"""

from __future__ import annotations

import json

from scripts.eval_progress_from_reports import (
    case_name,
    classify,
    collect,
    read_report,
    summarise,
)


def _report_html(
    *,
    head: str = "case-17-head",
    verdict: str = "BLOCKED",
    findings: list[tuple[str, str]] = (("MAJOR", "UNIQUE-01"),),
    rows: list[tuple[str, str]] = (("UNIQUE-01", "FAIL"),),
) -> str:
    finding_html = "".join(
        f'<div class="finding blocker"><h3>[{severity}] {cid}</h3></div>'
        for severity, cid in findings
    )
    row_html = "".join(
        f'<tr class="{"fail" if result == "FAIL" else "pass"}">'
        f"<td>{cid}</td><td class=\"req\">r</td><td></td><td>EXP-1</td>"
        f'<td class="diff">PASS &rarr; FAIL (head)</td>'
        f'<td class="{"fail" if result == "FAIL" else "pass"}">{result}</td>'
        f"<td>sha256:abc</td></tr>"
        for cid, result in rows
    )
    return (
        "<html><body><header><div class=\"summary\">"
        f"<div>Base: base</div><div>Head: {head}</div>"
        "</div>"
        f'<div class="verdict {"blocked" if verdict == "BLOCKED" else "verified"}">'
        f"{verdict}</div></header>"
        '<table><tbody>' + row_html + "</tbody></table>"
        f'<section><h2>Findings ({len(findings)})</h2>{finding_html}</section>'
        "</body></html>"
    )


def _truth(**fields) -> dict:
    return fields


def test_the_head_ref_names_the_case(tmp_path):
    path = tmp_path / "verification-report-1.html"
    path.write_text(_report_html(head="case-21-auth-head"), encoding="utf-8")
    assert case_name(read_report(path)["head_ref"]) == "case-21-auth"


def test_a_positive_case_with_the_expected_finding_is_a_pass(tmp_path):
    path = tmp_path / "verification-report-1.html"
    path.write_text(_report_html(), encoding="utf-8")
    report = read_report(path)
    result = classify(report, _truth(
        should_detect=True, expected_contract="UNIQUE-01", expected_min_findings=1,
    ))
    assert result["verdict"] == "PASS"
    assert result["matched"] == 1


def test_a_positive_case_without_the_expected_finding_is_a_miss(tmp_path):
    path = tmp_path / "verification-report-1.html"
    path.write_text(_report_html(findings=[], rows=[]), encoding="utf-8")
    report = read_report(path)
    result = classify(report, _truth(
        should_detect=True, expected_contract="UNIQUE-01", expected_min_findings=1,
    ))
    assert result["verdict"] == "MISS"


def test_a_positive_case_with_other_findings_is_unmatched_not_a_miss(tmp_path):
    """The evaluation ALSO matches by evidence type, so a case whose
    findings do not carry the expected contract id must not be counted
    as a miss by the progress read."""
    path = tmp_path / "verification-report-1.html"
    path.write_text(_report_html(findings=[("MAJOR", "CACHE-01")]), encoding="utf-8")
    report = read_report(path)
    result = classify(report, _truth(
        should_detect=True, expected_contract="UNIQUE-01", expected_min_findings=1,
    ))
    assert result["verdict"] == "UNMATCHED"


def test_a_negative_case_with_a_finding_is_a_false_positive(tmp_path):
    path = tmp_path / "verification-report-1.html"
    path.write_text(_report_html(), encoding="utf-8")
    report = read_report(path)
    result = classify(report, _truth(should_detect=False))
    assert result["verdict"] == "FALSE_POSITIVE"


def test_a_negative_case_without_a_finding_is_clean(tmp_path):
    path = tmp_path / "verification-report-1.html"
    path.write_text(_report_html(findings=[], rows=[]), encoding="utf-8")
    report = read_report(path)
    result = classify(report, _truth(should_detect=False))
    assert result["verdict"] == "PASS"


def test_collect_finds_the_case_directory_by_prefix(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "verification-report-1.html").write_text(
        _report_html(head="case-17-head"), encoding="utf-8"
    )
    cases = tmp_path / "golden-cases"
    case_dir = cases / "case-17-logic-inversion"
    case_dir.mkdir(parents=True)
    (case_dir / "ground-truth.json").write_text(
        json.dumps({
            "should_detect": True,
            "expected_contract": "UNIQUE-01",
            "expected_min_findings": 1,
        }),
        encoding="utf-8",
    )
    entries = collect(reports, cases)
    assert [e["case"] for e in entries] == ["case-17"]
    assert entries[0]["verdict"] == "PASS"
    counts = summarise(entries)
    assert counts == {
        "cases": 1,
        "positive": 1,
        "negative": 0,
        "detected": 1,
        "missed": 0,
        "unmatched": 0,
        "false_positive": 0,
        "clean": 0,
    }


def test_collect_keeps_the_newest_report_per_case(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    old = reports / "verification-report-1.html"
    old.write_text(_report_html(findings=[]), encoding="utf-8")
    new = reports / "verification-report-2.html"
    new.write_text(_report_html(findings=[("MAJOR", "UNIQUE-01")]), encoding="utf-8")
    import os
    os.utime(old, (1, 1))
    cases = tmp_path / "golden-cases"
    case_dir = cases / "case-17-logic-inversion"
    case_dir.mkdir(parents=True)
    (case_dir / "ground-truth.json").write_text(
        json.dumps({
            "should_detect": True,
            "expected_contract": "UNIQUE-01",
            "expected_min_findings": 1,
        }),
        encoding="utf-8",
    )
    entries = collect(reports, cases)
    assert len(entries) == 1
    assert entries[0]["verdict"] == "PASS"


def test_a_window_excludes_the_reports_of_earlier_runs(tmp_path):
    """The output directory keeps every run's reports; a progress read
    without a window would mix this week with this run."""
    import os
    import time

    reports = tmp_path / "reports"
    reports.mkdir()
    old = reports / "verification-report-1.html"
    old.write_text(_report_html(head="case-17-head"), encoding="utf-8")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    cases = tmp_path / "golden-cases"
    case_dir = cases / "case-17-logic-inversion"
    case_dir.mkdir(parents=True)
    (case_dir / "ground-truth.json").write_text(
        json.dumps({"should_detect": True, "expected_contract": "UNIQUE-01"}),
        encoding="utf-8",
    )
    assert len(collect(reports, cases)) == 1
    assert len(collect(reports, cases, since=time.time() - 60)) == 0
