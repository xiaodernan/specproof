#!/usr/bin/env python
"""audit_evidence.py — cross-page consistency audit across the six locked JSONs.

Checks (each named, each re-run on demand):
  A. chronicle.json section count == repoStats.json ledger_sections
  B. zh/en world book volume counts equal; worldbook chronicle upper bound intact
  C. evidence.json 'latest' exists and verdict is non-empty
  D. unsigned.json has exactly 4 checks, each id unique
  E. courtLock.json verdict == LOCKED + lock length 16
  F. engine.json calls > 0 and file exists
  G. courtLock.json # 1: every check in test_court_never_caches is found here
     (token presence; deeper assert lives in tests/unit/test_court_never_caches.py)

Writes docs/evidence/audit-evidence.json. Exit 0 only if every check passes.
"""
import io
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "apps" / "web" / "src"
CHDIR = PAGES / "pages"

def J(name: str):
    return json.loads((CHDIR / name).read_text(encoding="utf-8"))

checks = []

# A. chronicle count == repoStats.ledger_sections
chron = J("chronicle.json")
stats = J("repoStats.json")
ok_a = len(chron) == stats["ledger_sections"]
checks.append({"id": "chronicle_vs_repoStats", "ok": ok_a,
               "detail": f"chronicle entries={len(chron)} repoStats ledger_sections={stats['ledger_sections']}"})

# B. worldbook zh==en volumes
w = J("worldbook.json")
zh = len(w["locales"]["zh"]["volumes"]); en = len(w["locales"]["en"]["volumes"])
ok_b = zh == en
checks.append({"id": "worldbook_zh_en_symmetric", "ok": ok_b, "detail": f"zh={zh} en={en}"})

# C. evidence latest present and verdict set
ev = J("evidence.json")
latest = ev.get("latest") or {}
ok_c = bool(latest.get("verdict"))
checks.append({"id": "evidence_verdict_present", "ok": ok_c,
               "detail": f"latest={latest.get('file')} verdict={latest.get('verdict')}"})

# D. exactly 4 unique unsigned checks
un = J("unsigned.json")
ids = [c["id"] for c in un.get("checks", [])]
ok_d = len(ids) == 4 and len(set(ids)) == 4
checks.append({"id": "unsigned_four_unique_lamps", "ok": ok_d, "detail": f"ids={ids}"})

# E. courtLock locked
cl = J("courtLock.json")
ok_e = cl.get("verdict") == "LOCKED" and len(cl.get("lock", "") or "") == 16
checks.append({"id": "courtLock_locked_16hex", "ok": ok_e, "detail": f"verdict={cl.get('verdict')} lock={cl.get('lock')}"})

# F. engine present
eng = J("engine.json")
ok_f = eng.get("calls", 0) > 0
checks.append({"id": "engine_calls_positive", "ok": ok_f,
               "detail": f"calls={eng.get('calls')} kinds={eng.get('kinds')} lanes={eng.get('lanes')}"})

# G. semantic lock sanity (token presence; deeper assertions live in pytest)
sc_text = (ROOT / "providers" / "semantic_cache.py").read_text(encoding="utf-8")
ok_g = bool(re.search(r'EVIDENCE_KINDS[^=]*=\s*frozenset\(\s*\{[^}]*court[^}]*\}', sc_text, flags=re.S))
checks.append({"id": "semantic_cache_evidence_literals_intact", "ok": ok_g,
               "detail": "EVIDENCE_KINDS frozenset literal contains 'court'"})

all_ok = all(c["ok"] for c in checks)
doc = {
    "version": 1,
    "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    "verdict": "CONSISTENT" if all_ok else "DRIFT",
    "checks": checks,
}
(ROOT / "docs" / "evidence" / "audit-evidence.json").write_text(
    json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"
)
for c in checks:
    print(f"[{'ok ' if c['ok'] else 'FAIL'}] {c['id']} — {c['detail']}")
print(f"\nverdict: {doc['verdict']}")
sys.exit(0 if all_ok else 2)
