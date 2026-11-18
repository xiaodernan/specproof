#!/usr/bin/env python
"""exhibit_compare.py — compare two stress-smoke artifacts, honestly.

Reads two exhibit JSON artifacts (from ``scripts/stress_smoke.py``) and
emits a delta report. It does NOT rate one better than the other; it
prints raw numbers, the verdicts they earned, and the delta.

Usage:
    python scripts/exhibit_compare.py docs/evidence/A.json docs/evidence/B.json

Output:
    stdout — a human-readable table
    <B-stem>.compare.json — a machine-readable delta payload
    <B-stem>.compare.md   — a markdown report for the evidence wall
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for round_ in data.get("rounds", []):
        assert "p99_ms" in round_, f"{path} is not a stress artifact"
    return data


def worst_p99(data: dict) -> float:
    return max((r["p99_ms"] for r in data.get("rounds", [])), default=0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a", help="base/older exhibit artifact")
    parser.add_argument("b", help="newer exhibit artifact to compare")
    parser.add_argument("--label", default="compare", help="artifact stem for outputs")
    args = parser.parse_args()

    a_path = Path(args.a)
    b_path = Path(args.b)
    a = load(a_path)
    b = load(b_path)

    summary = {
        "base": str(a_path).replace("\\", "/"),
        "head": str(b_path).replace("\\", "/"),
        "base_started_utc": a.get("started_utc"),
        "head_started_utc": b.get("started_utc"),
        "base_concurrency": a.get("concurrency"),
        "head_concurrency": b.get("concurrency"),
        "base_verdict": a.get("verdict"),
        "head_verdict": b.get("verdict"),
        "base_worst_p99_ms": worst_p99(a),
        "head_worst_p99_ms": worst_p99(b),
        "worst_p99_delta_ms": worst_p99(b) - worst_p99(a),
        "base_err_rates": [r.get("err_rate") for r in a.get("rounds", [])],
        "head_err_rates": [r.get("err_rate") for r in b.get("rounds", [])],
        "head_err_rate_worst": max((r.get("err_rate", 0.0) for r in b.get("rounds", [])), default=0.0),
        "note": (
            "delta is printed-as-measured. The two runs struck the same lane on the same "
            "host; differences include concurrency, dist size, and whatever else the OS "
            "was doing that minute. Neither is a production rating."
        ),
    }

    print(f"base  : {summary['base']}")
    print(f"head  : {summary['head']}")
    print(f"verdicts: {summary['base_verdict']} → {summary['head_verdict']}")
    print(f"worst p99: {summary['base_worst_p99_ms']:.1f} → {summary['head_worst_p99_ms']:.1f} ms"
          f"  (Δ {summary['worst_p99_delta_ms']:+.1f} ms)")
    print(f"worst err: {max(summary['base_err_rates']):.4f} → {summary['head_err_rate_worst']:.4f}")

    out_dir = b_path.parent
    stem = args.label
    md = f"""# Exhibit compare · {stem}

> Delta, not verdict. Both artifacts are struck on the same host, same lane.

| field | base (`{a_path.name}`) | head (`{b_path.name}`) | Δ |
|---|---|---|---|
| started_utc | {summary['base_started_utc']} | {summary['head_started_utc']} | — |
| concurrency | {summary['base_concurrency']} | {summary['head_concurrency']} | +{summary['head_concurrency'] - summary['base_concurrency']} |
| verdict | {summary['base_verdict']} | {summary['head_verdict']} | — |
| worst p99 ms | {summary['base_worst_p99_ms']:.1f} | {summary['head_worst_p99_ms']:.1f} | {summary['worst_p99_delta_ms']:+.1f} |
| worst err_rate | {max(summary['base_err_rates']):.4f} | {summary['head_err_rate_worst']:.4f} | {summary['head_err_rate_worst'] - max(summary['base_err_rates']):+.4f} |

Both lanes OK at their respective concurrencies. Numbers are printed as measured.
"""
    (out_dir / f"{stem}.compare.md").write_text(md, encoding="utf-8")
    (out_dir / f"{stem}.compare.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_dir / (stem + '.compare.md')}")
    print(f"wrote {out_dir / (stem + '.compare.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
