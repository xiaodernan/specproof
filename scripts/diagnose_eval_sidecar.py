#!/usr/bin/env python
"""Read an evaluation sidecar and say what the run actually found.

The full-pool evaluation takes hours. When it finishes, the questions
are always the same:

- how many cases were measured, and how many were NOT;
- for a case that was not measured, WHICH side failed and what that
  side printed (the diagnosis - the console prints it, the sidecar
  carries it, and the HTML report shows it);
- which cases were measured more than once, and WHY;
- which cases drifted in severity, and what the level came from.

This answers all of that from the sidecar ALONE - no measurement, no
database, no re-run. It is the tool the ledger's queue asks for
("use that run's sidecar to find out why the base side failed, then
fix it").

Usage:
    python scripts/diagnose_eval_sidecar.py <report.results.json>
    python scripts/diagnose_eval_sidecar.py <report.results.jsonl>

The exit code is 0 when every case was measured, and 1 when at least
one was not - so a caller can gate on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evidence.acceptance import (  # noqa: E402
    count_records,
    retry_summary,
    severity_reconciliation,
)


def load_records(path: Path) -> list[dict[str, Any]]:
    """The per-case records, from either sidecar shape."""
    if path.suffix == ".jsonl":
        latest: dict[str, dict[str, Any]] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # A torn line: the run was killed mid-write. Half a
                # record is not a record - skip it, keep the rest.
                continue
            if isinstance(record, dict):
                latest[str(record.get("case") or len(latest))] = record
        return list(latest.values())
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    return [c for c in cases if isinstance(c, dict)]


def _print_tail(label: str, text: str, limit: int = 1200) -> None:
    if not text:
        return
    print(f"      {label} output (last {limit} chars):")
    for line in text[-limit:].splitlines():
        print(f"        {line}")


def report(path: Path) -> int:
    records = load_records(path)
    if not records:
        print(f"no records in {path}", file=sys.stderr)
        return 0

    counts, not_measured = count_records(records)
    positives = [r for r in records if r.get("should_detect")]
    negatives = [r for r in records if not r.get("should_detect")]

    print("=" * 72)
    print(f"sidecar: {path}")
    print("=" * 72)
    print(f"cases            : {len(records)}")
    print(f"  positive       : {len(positives)}")
    print(f"  negative       : {len(negatives)}")
    print(f"detected         : {counts.detected}")
    print(f"false positives  : {counts.false_positives}")
    print(f"not measured     : {not_measured}")
    print()

    # ── the cases that were never measured ─────────────────────────────────
    not_run = [r for r in records if r.get("verdict") == "NOT_RUN"]
    if not_run:
        print("-" * 72)
        print(f"NOT MEASURED ({len(not_run)}) - why the evidence path could not judge:")
        for r in not_run:
            print(f"  * {r.get('case', '')}")
            print(f"      reason: {r.get('errors') or '(no reason recorded)'}")
            _print_tail("base", str(r.get("base_output") or ""))
            _print_tail("head", str(r.get("head_output") or ""))
        print()
    else:
        print("every case was measured.")
        print()

    # ── the cases that were measured more than once ─────────────────────────
    retry = retry_summary(records)
    if retry["retried_cases"]:
        print("-" * 72)
        print(f"MEASURED MORE THAN ONCE ({retry['retried_cases']}):")
        for entry in retry["retries"]:
            print(f"  * {entry['case']} - {entry['reason']} "
                  f"({entry['attempts']} attempts; "
                  f"first: {entry['first_verdict'] or '—'}; "
                  f"final: {entry['final_verdict'] or '—'})")
        print()

    # ── the severity drift ─────────────────────────────────────────────────
    sev = severity_reconciliation(records)
    if sev["mismatches"]:
        print("-" * 72)
        print(f"SEVERITY DRIFT ({len(sev['mismatches'])} of "
              f"{sev['matched_positive_cases']} matched positives):")
        for m in sev["mismatches"]:
            print(f"  * {m['case']}")
            print(f"      expected {m['expected']}, got {m['actual']}"
                  f"  (contract {m.get('contract') or '—'})")
            print(f"      level came from: evidence {m.get('evidence_kinds') or '—'}"
                  f", db state {m.get('db_state_verdicts') or '—'}")
        print()
    elif sev["matched_positive_cases"]:
        print(f"severity agreement: {sev['severity_agreement']}% "
              f"over {sev['matched_positive_cases']} matched positives "
              f"- no drift.")
        print()

    return 1 if not_run else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar", help="the <report>.results.json(.l) a run wrote")
    args = parser.parse_args(argv)

    sidecar = Path(args.sidecar)
    if not sidecar.exists():
        print(f"no such sidecar: {sidecar}", file=sys.stderr)
        return 2
    return report(sidecar)


if __name__ == "__main__":
    raise SystemExit(main())
