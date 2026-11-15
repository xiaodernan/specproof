#!/usr/bin/env python
"""Build evidence.json — the git-tracked stress evidence, distilled for `#/fabric`.

Reads docs/evidence/*.json (written by scripts/stress_smoke.py --json-report) and
emits a compact summary into apps/web/src/pages/evidence.json. The figures are
verbatim from the machine that produced them; nothing is recomputed, averaged,
or smoothed. If the directory is empty we emit an honest "no evidence filed yet"
document instead of fabricating a green row.
"""
import io
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"
OUT = ROOT / "apps" / "web" / "src" / "pages" / "evidence.json"

files = sorted(EVIDENCE.glob("*.json"), key=lambda p: p.name)
picked = []
for f in files:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        picked.append({"file": f.name, "readable": False})
        continue
    rounds = data.get("rounds", [])
    worst_p99 = max((r.get("p99_ms", 0) for r in rounds), default=0.0)
    total_ok = sum(r.get("ok", 0) for r in rounds)
    total = sum(r.get("total", 0) for r in rounds)
    bytes_read = sum(r.get("bytes_read", 0) for r in rounds)
    picked.append({
        "file": f.name,
        "readable": True,
        "started_utc": data.get("started_utc", ""),
        "note": data.get("note", ""),
        "concurrency": data.get("concurrency"),
        "warmup_rounds": data.get("warmup_rounds", 0),
        "rounds": [
            {
                "total": r.get("total"),
                "ok": r.get("ok"),
                "p50_ms": r.get("p50_ms"),
                "p95_ms": r.get("p95_ms"),
                "p99_ms": r.get("p99_ms"),
            }
            for r in rounds
        ],
        "worst_p99_ms": worst_p99,
        "total": total,
        "total_ok": total_ok,
        "bytes_read": bytes_read,
        "verdict": data.get("verdict", "unknown"),
    })

# newest first by filename convention (YYYY-MM-DD-name.json)
picked.sort(key=lambda p: p.get("file", ""), reverse=True)
doc = {
    "version": 1,
    "source": "docs/evidence/*.json (stress_smoke.py --json-report output; this host)",
    "files_count": len(picked),
    "latest": picked[0] if picked else None,
    "all": picked,
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"evidence.json: {len(picked)} file(s); latest -> {(picked[0]['file'] if picked else 'none')}")
