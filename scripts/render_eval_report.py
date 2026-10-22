#!/usr/bin/env python
"""Re-render an evaluation report from its sidecar.

The HTML report is a VIEW of the evidence, not a second copy of it. The
sidecar (``<report>.results.json``) holds the per-case records and the
acceptance verdict; this script turns them back into the report page.

Why it exists (ledger #411): the report used to be rendered once, at the
end of a run, by whichever build happened to be running. A later build
that improves the report (the contract's level in the table, the drift
list, the "not measured" section) therefore could not reach the
existing reports without measuring the pool AGAIN - which costs hours
per run. With this script the evidence stays put and the report can be
regenerated from it.

Usage:
    python scripts/render_eval_report.py <report.results.json> [-o out.html]

The sidecar is read; nothing is measured and no database is touched.
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

from evidence.acceptance import AcceptanceResult  # noqa: E402
from evidence.report import render_eval_report  # noqa: E402


def load_evidence(
    path: Path,
) -> tuple[list[dict[str, Any]], AcceptanceResult | None]:
    """The per-case records and (when there is one) the verdict.

    Two shapes are accepted:

    - ``<report>.results.json`` - the final sidecar: the records plus the
      acceptance verdict the run decided;
    - ``<report>.results.jsonl`` - the incremental records a run writes as
      it goes. They exist even for a run that was killed half way, and
      there is NO acceptance verdict for such a run - so none is
      invented (an acceptance card that was never decided would be a
      verdict nobody reached).
    """
    if path.suffix == ".jsonl":
        latest: dict[str, dict[str, Any]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            latest[str(record.get("case") or len(latest))] = record
        return list(latest.values()), None
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    raw_acceptance = data.get("acceptance")
    acceptance = (
        AcceptanceResult.from_dict(raw_acceptance)
        if isinstance(raw_acceptance, dict)
        else None
    )
    return cases, acceptance


def render_from_sidecar(sidecar_path: Path) -> str:
    """The report page for the evidence in a sidecar file."""
    cases, acceptance = load_evidence(sidecar_path)
    return render_eval_report(cases, acceptance)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sidecar",
        help="the <report>.results.json (or .results.jsonl) a run wrote",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="where to write the HTML (default: beside the sidecar)",
    )
    args = parser.parse_args(argv)

    sidecar = Path(args.sidecar)
    if not sidecar.exists():
        print(f"no such sidecar: {sidecar}", file=sys.stderr)
        return 2
    cases, acceptance = load_evidence(sidecar)
    html = render_eval_report(cases, acceptance)
    out = (
        Path(args.output)
        if args.output
        else sidecar.with_suffix("").with_suffix(".html")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{len(cases)} case record(s) rendered into {out}")
    if acceptance is None:
        print(
            "no acceptance verdict in this sidecar - the report carries none "
            "(a verdict nobody decided must not be shown)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
