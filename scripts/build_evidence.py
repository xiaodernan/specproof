import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"
OUT = ROOT / "apps" / "web" / "src" / "pages" / "evidence.json"


def distill(f: Path) -> dict:
    data = json.loads(f.read_text(encoding="utf-8"))
    rounds = data.get("rounds", [])
    worst_p99 = max((r.get("p99_ms", 0) for r in rounds), default=0.0)
    avg_p95 = sum(r.get("p95_ms", 0) for r in rounds) / len(rounds) if rounds else 0.0
    total_ok = sum(r.get("ok", 0) for r in rounds)
    total = sum(r.get("total", 0) for r in rounds)
    bytes_read = sum(r.get("bytes_read", 0) for r in rounds)
    return {
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
        "avg_p95_ms": avg_p95,
        "total": total,
        "total_ok": total_ok,
        "bytes_read": bytes_read,
        "verdict": data.get("verdict", "unknown"),
    }


files = sorted(EVIDENCE.glob("*.json"))
picked = []
for f in files:
    try:
        picked.append(distill(f))
    except (json.JSONDecodeError, UnicodeDecodeError):
        picked.append({"file": f.name, "readable": False})

# newest first: ISO started_utc sorts lexicographically; unreadable files sink.
def sort_key(p: dict) -> tuple[int, str]:
    if p.get("readable") is False:
        return (0, "")
    return (1, str(p.get("started_utc", "")))


picked.sort(key=sort_key, reverse=True)

EXHIBIT_RE = re.compile(r"static-(warm|light)(-[0-9-]+)?\.json$")

def is_exhibit(p: dict) -> bool:
    return bool(p.get("readable") is not False and EXHIBIT_RE.search(str(p.get("file", ""))))

latest = picked[0] if picked else None
exhibits = [p for p in picked if is_exhibit(p)]
delta = None
if len(exhibits) >= 2:
    cur, prev = exhibits[0], exhibits[1]
    delta = {
        "vs_file": prev["file"],
        "worst_p99_delta_ms": cur["worst_p99_ms"] - prev["worst_p99_ms"],
        "avg_p95_delta_ms": cur["avg_p95_ms"] - prev["avg_p95_ms"],
        "bytes_delta": cur["bytes_read"] - prev["bytes_read"],
        "total_delta": cur["total"] - prev["total"],
    }

doc = {
    "version": 1,
    "source": "docs/evidence/*.json (stress_smoke.py --json-report output; this host)",
    "files_count": len(picked),
    "exhibits_count": len(exhibits),
    "latest": latest,
    "delta_vs_previous": delta,
    "all": picked,
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
latest_name = latest["file"] if latest else "none"
print(f"evidence.json: {len(picked)} file(s); {len(exhibits)} exhibit(s); latest -> {latest_name}; delta -> {delta!r}")
