#!/usr/bin/env python
"""monthly_census.py — render docs/evidence/monthly-census.md.

A 7-ish-day windowed table of every stress exhibit struck on this host.
Only files carrying a `rounds` list count as evidence; audit-*.json artifacts are excluded.
"""
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs" / "evidence"
OUT = EVID / "monthly-census.md"

by_window: dict[str, list[dict]] = defaultdict(list)
total_ok = 0
total_req = 0
for f in sorted(EVID.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        continue
    if "rounds" not in raw:
        continue
    started = raw.get("started_utc") or ""
    for r in raw.get("rounds", []):
        total_ok += int(r.get("ok", 0) or 0)
        total_req += int(r.get("total", 0) or 0)
    key = started[:7] if started else "unknown"
    by_window[key].append({
        "file": f.name,
        "started_utc": started,
        "p50": min((r.get("p50_ms", 0) for r in raw["rounds"]), default=0),
        "p99": max((r.get("p99_ms", 0) for r in raw["rounds"]), default=0),
        "ok": sum(int(r.get("ok", 0) or 0) for r in raw["rounds"]),
        "total": sum(int(r.get("total", 0) or 0) for r in raw["rounds"]),
        "verdict": raw.get("verdict", "unknown"),
    })

lines = [
    f"# Monthly Census — generated {datetime.now(UTC).isoformat(timespec='seconds')}",
    "",
    f"total requests: **{total_req:,}** · total 2xx/3xx: **{total_ok:,}** · ratio: **{(total_ok / total_req * 100 if total_req else 0):.2f}%**",
    "",
]
for window in sorted(by_window, reverse=True):
    lines.append(f"## {window}")
    lines.append("| exhibit | struck | p50 | p99 | verdict | req ok/total |")
    lines.append("|---|---|---|---|---|---|")
    for e in by_window[window]:
        lines.append(f"| `{e['file']}` | {e['started_utc'][:16]} | {e['p50']:.1f}ms | {e['p99']:.1f}ms | {e['verdict']} | {e['ok']}/{e['total']} |")
    lines.append("")
lines += [
    "_Live testimony of scripts/monthly_census.py — every number above is derived from git-tracked stress artifacts._",
    "",
]
OUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
print(f"wrote {OUT} ({len(by_window)} window(s))")
