#!/usr/bin/env python
"""build_tally.py — merge every existing evidence artifact into one machine-readable roll-up.

No new audits are invented, no network I/O is performed, no assertions are skipped.
Every field here is a verbatim pointer into the artifact it came from; the union is the tally.
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs" / "evidence"
PAGES = ROOT / "apps" / "web" / "src" / "pages"


def j(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    u = j(PAGES / "unsigned.json")
    e = j(PAGES / "evidence.json")
    c = j(PAGES / "courtLock.json")
    p = j(PAGES / "purity_sift.json")
    _ch = j(PAGES / "chronicle.json")
    rs = j(PAGES / "repoStats.json")
    wb = j(PAGES / "worldbook.json")
    a = j(PAGES / "audit_chain.json")

    doc = {
        "version": 1,
        "source": "merged verbatim from unsigned/evidence/courtLock/purity/audit_chain/chronicle/repoStats/worldbook JSON",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "totals": {
            "commits": rs.get("git_commit_count"),
            "chronicle_sections": rs.get("ledger_sections"),
            "worldbook_volumes_zh": len(wb.get("locales", {}).get("zh", {}).get("volumes", [])),
            "worldbook_volumes_en": len(wb.get("locales", {}).get("en", {}).get("volumes", [])),
            "python_test_files": rs.get("python_test_files"),
            "web_test_files": rs.get("web_test_files"),
        },
        "lamps": {
            "unsigned_phase": u.get("generated_utc"),
            "weekly_stress_merged": next((c.get("status") for c in u.get("checks", []) if c.get("id") == "weekly-stress-merged"), "unknown"),
            "port_8000": next((c.get("status") for c in u.get("checks", []) if c.get("id") == "port-8000-answers"), "unknown"),
            "branch_cleanliness": next((c.get("status") for c in u.get("checks", []) if c.get("id") == "branch-cleanliness"), "unknown"),
            "observability_signature": next((c.get("status") for c in u.get("checks", []) if c.get("id") == "observability-signature"), "unknown"),
            "court_lock_verdict": c.get("verdict"),
            "court_lock_hex": c.get("lock"),
            "purity_verdict": p.get("verdict"),
            "purity_tracked_files": p.get("tracked_files"),
            "purity_hits": p.get("unexpected_hits"),
        },
        "stress": {
            "latest_file": e.get("latest", {}).get("file") if e.get("latest") else None,
            "latest_p99_ms": round((e.get("latest") or {}).get("worst_p99_ms", 0), 3) if e.get("latest") else None,
            "latest_verdict": (e.get("latest") or {}).get("verdict"),
            "files_count": e.get("files_count"),
            "delta_p99_ms": round((e.get("delta_vs_previous") or {}).get("worst_p99_delta_ms", 0), 3) if e.get("delta_vs_previous") else None,
        },
        "evidence_graph": {
            "chain_verdict": a.get("verdict"),
            "chain_lanes": a.get("lane_count"),
            "chain_generated_utc": a.get("generated_utc"),
        },
        "book": {
            "zh_bytes": rs.get("world_bytes_zh"),
            "en_bytes": rs.get("world_bytes_en"),
            "ledger_bytes_kB": rs.get("ledger_bytes_kB"),
        },
    }
    (EVID / "tally.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote docs/evidence/tally.json · verdict:", doc["evidence_graph"]["chain_verdict"], "· lamps:", len(doc["lamps"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
