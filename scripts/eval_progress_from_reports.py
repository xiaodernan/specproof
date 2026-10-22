"""How far has the golden-case evaluation got, read from the per-case reports.

The evaluation runs the whole pipeline per case, and the pipeline writes
ONE report per case into the output directory as it goes. The
evaluation's OWN record — the sidecar with the metrics, the pool
snapshot, the per-case records — is written at the END of the run. A run
that is still going therefore has no summary to read: the only things on
disk are the per-case reports.

This script reads those reports and says, per case, what the pipeline
found, and (against the case's ground truth) whether the expected defect
was caught. It is a PROGRESS READ, and it says so:

- the numbers it prints are DERIVED from the reports, not the evaluation's
  own numbers;
- the evaluation's own metrics come from its sidecar, and the run's own
  numbers win when they exist;
- the matching rule it uses is the evaluation's rule, with ONE documented
  exception (the evidence-type fallback), and a case that the fallback
  could have matched is reported as "unmatched" rather than silently
  counted.

    python scripts/eval_progress_from_reports.py \
        --reports reports --cases golden-cases
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any

#: ``<div>Head: case-17-head</div>`` — the case is named by its head ref.
_HEAD_REF = re.compile(r"<div>Head:\s*([^<]*)</div>")
#: ``<div class="verdict blocked">BLOCKED</div>``.
_VERDICT = re.compile(r'<div class="verdict [a-z]+">([^<]*)</div>')
#: One finding: ``<h3>[BLOCKER] AUTH-01</h3>``.
_FINDING = re.compile(r"<h3>\[([A-Z]+)\]\s*([^<]*)</h3>")
#: One matrix row: the cells of the row, in order.
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
#: The report's own tag-free text of a cell.
_TAG = re.compile(r"<[^>]+>")

#: The evaluation's own matching rule, minus the evidence-type fallback:
#: a finding matches when its contract id IS the expected one.
_EXPECTED_EVIDENCE_NOTE = (
    "the evaluation ALSO matches a finding by its evidence type; a case "
    "whose findings do not carry the expected contract id is reported as "
    "'unmatched' here, not as a miss"
)


def _text(cell: str) -> str:
    return unescape(_TAG.sub(" ", cell)).replace("\xa0", " ").strip()


def read_report(path: Path) -> dict[str, Any]:
    """What one per-case report says."""
    html = path.read_text(encoding="utf-8", errors="replace")
    head = _HEAD_REF.search(html)
    verdict = _VERDICT.search(html)
    rows: list[dict[str, str]] = []
    for raw in _ROW.findall(html):
        cells = [_text(cell) for cell in _CELL.findall(raw)]
        if len(cells) < 6:
            continue
        contract_id = cells[0]
        if not contract_id or " " in contract_id:
            # The preflight table's rows are not matrix rows.
            continue
        rows.append({
            "contract_id": contract_id,
            "result": cells[5],
            "evidence": cells[6] if len(cells) > 6 else "",
        })
    findings = [
        {"severity": severity, "contract_id": contract_id.strip()}
        for severity, contract_id in _FINDING.findall(html)
    ]
    return {
        "path": path,
        "head_ref": head.group(1).strip() if head else "",
        "verdict": verdict.group(1).strip() if verdict else "",
        "rows": rows,
        "findings": findings,
    }


def case_name(head_ref: str) -> str:
    """``case-17-head`` -> ``case-17``."""
    name = head_ref.strip()
    if name.endswith("-head"):
        name = name[: -len("-head")]
    return name


def case_dir(cases_dir: Path, case: str) -> Path | None:
    """The golden case DIRECTORY for a short case id.

    The reports name the case by its head ref (``case-17``), while the
    directories carry the slug as well (``case-17-logic-inversion``) ⇒ ⇒ ⇒
    the directory is found by prefix, and only when it is unambiguous.
    """
    matches = sorted(
        d for d in cases_dir.glob(f"{case}*") if (d / "ground-truth.json").exists()
    )
    if len(matches) == 1:
        return matches[0]
    return None


def ground_truth(cases_dir: Path, case: str) -> dict[str, Any]:
    directory = case_dir(cases_dir, case)
    if directory is None:
        return {}
    path = directory / "ground-truth.json"
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def classify(report: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    """This case's verdict, by the evaluation's own rule."""
    findings = report["findings"]
    expected = str(truth.get("expected_contract") or "")
    min_findings = int(truth.get("expected_min_findings", 1) or 1)
    should_detect = bool(truth.get("should_detect", False))
    if not truth:
        return {"verdict": "UNKNOWN", "matched": 0, "reason": "no ground truth"}
    if not should_detect:
        if findings:
            return {
                "verdict": "FALSE_POSITIVE",
                "matched": 0,
                "reason": f"{len(findings)} finding(s) on a negative case",
            }
        return {"verdict": "PASS", "matched": 0, "reason": "no finding"}
    matched = [f for f in findings if f["contract_id"] == expected]
    if len(matched) >= min_findings:
        return {"verdict": "PASS", "matched": len(matched), "reason": "expected contract found"}
    if matched:
        return {
            "verdict": "PARTIAL",
            "matched": len(matched),
            "reason": "expected contract found, fewer than required",
        }
    if findings:
        return {
            "verdict": "UNMATCHED",
            "matched": 0,
            "reason": (
                f"{len(findings)} finding(s), none carrying {expected!r} "
                f"— the evidence-type rule might still match them"
            ),
        }
    return {"verdict": "MISS", "matched": 0, "reason": "no finding"}


def collect(
    reports_dir: Path,
    cases_dir: Path,
    since: float | None = None,
) -> list[dict[str, Any]]:
    """One entry per case that has a report (the newest report wins).

    ``since`` is a POSIX timestamp: the output directory accumulates the
    reports of EVERY run, so a progress read without a time window would
    mix this run's cases with the ones from the last week.

    A window can still contain more than ONE run: an integration test
    that runs the evaluation on a subset writes its reports into the same
    directory, and it overlaps a long run. Each entry therefore carries
    how many reports that case has in the window (``reports_in_window``)
    ⇒ ⇒ ⇒ the reader can see whether the window holds one run or several
    ⇒ ⇒ ⇒ and the summary says so, because a case's verdict taken from
    the newest report may belong to the OTHER run.
    """
    by_case: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(reports_dir.glob("verification-report-*.html")):
        if since is not None and path.stat().st_mtime < since:
            continue
        report = read_report(path)
        case = case_name(report["head_ref"])
        if not case.startswith("case-"):
            continue
        by_case.setdefault(case, []).append(report)
    out: list[dict[str, Any]] = []
    for case in sorted(by_case):
        reports = sorted(by_case[case], key=lambda r: r["path"].stat().st_mtime)
        report = reports[-1]
        truth = ground_truth(cases_dir, case)
        out.append({
            "case": case,
            "report": report,
            "truth": truth,
            "reports_in_window": len(reports),
            **classify(report, truth),
        })
    return out


def summarise(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "cases": len(entries),
        "positive": 0,
        "negative": 0,
        "detected": 0,
        "missed": 0,
        "unmatched": 0,
        "false_positive": 0,
        "clean": 0,
    }
    for entry in entries:
        truth = entry["truth"]
        if not truth:
            continue
        if truth.get("should_detect"):
            counts["positive"] += 1
            if entry["verdict"] == "PASS":
                counts["detected"] += 1
            elif entry["verdict"] == "MISS":
                counts["missed"] += 1
            elif entry["verdict"] == "UNMATCHED":
                counts["unmatched"] += 1
        else:
            counts["negative"] += 1
            if entry["verdict"] == "FALSE_POSITIVE":
                counts["false_positive"] += 1
            else:
                counts["clean"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", default="reports", help="the output directory")
    parser.add_argument("--cases", default="golden-cases", help="the golden cases directory")
    parser.add_argument("--only", default=None, help="print one case only")
    parser.add_argument(
        "--minutes",
        type=float,
        default=None,
        help="only read the reports written in the last N minutes "
             "(the output directory keeps the reports of every run)",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="only read the reports written at or after this ISO timestamp, "
             "e.g. 2026-10-22T01:16:00 (the moment a run started)",
    )
    args = parser.parse_args(argv)

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since).timestamp()
    elif args.minutes is not None:
        since = time.time() - args.minutes * 60
    entries = collect(Path(args.reports), Path(args.cases), since)
    if args.only:
        entries = [e for e in entries if e["case"] == args.only]
    if not entries:
        print("no per-case reports found — is the evaluation running?")
        return 0

    print(
        f"{'case':<44} {'expect':<8} {'verdict':<15} {'matched':<8} note"
    )
    for entry in entries:
        expect = (
            "detect"
            if entry["truth"].get("should_detect")
            else "clean"
            if entry["truth"]
            else "?"
        )
        print(
            f"{entry['case']:<44} {expect:<8} {entry['verdict']:<15} "
            f"{entry['matched']:<8} {entry['reason']}"
        )
    counts = summarise(entries)
    print("")
    print(f"cases with a report: {counts['cases']}")
    print(
        f"positive: {counts['positive']} "
        f"(detected {counts['detected']}, missed {counts['missed']}, "
        f"unmatched {counts['unmatched']})"
    )
    print(
        f"negative: {counts['negative']} "
        f"(false positives {counts['false_positive']}, clean {counts['clean']})"
    )
    print("")
    print("PROGRESS READ, derived from the per-case reports — the evaluation's own")
    print("metrics come from its sidecar and win when the run has finished.")
    print(f"Note: {_EXPECTED_EVIDENCE_NOTE}.")
    more_than_one = [
        e["case"] for e in entries if e.get("reports_in_window", 1) > 1
    ]
    if more_than_one:
        # A window can hold more than one run (an integration test that
        # runs the evaluation on a subset writes into the same directory).
        # A case measured twice may have been measured by DIFFERENT runs,
        # and the verdict above is the newest one ⇒ ⇒ ⇒ the counts are a
        # mixture, and the reader has to know that.
        print("")
        print(
            f"!! {len(more_than_one)} case(s) have more than one report in this "
            f"window, so the window holds MORE THAN ONE run: "
            f"{', '.join(more_than_one[:8])}"
            f"{' ...' if len(more_than_one) > 8 else ''}"
        )
        print(
            "   the verdict shown is the NEWEST report's -> the counts above "
            "MIX the runs -> use a window that holds one run, or read the "
            "evaluation's own sidecar for the authoritative numbers"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
