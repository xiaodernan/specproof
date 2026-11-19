#!/usr/bin/env python
"""emit_audit_notice.py — distil docs/evidence/audit-chain.md into a compact JSON.

Writes apps/web/src/pages/audit_chain.json. The frontend reads it as ink,
not as data plumbing; nothing here calls a network.
"""
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "evidence" / "audit-chain.md"
OUT = ROOT / "apps" / "web" / "src" / "pages" / "audit_chain.json"


def parse():
    if not SRC.exists():
        return {}
    text = SRC.read_text(encoding="utf-8")
    m = re.search(r"verdict:\s*\*\*(\w+)\*\*", text)
    verdict = m.group(1) if m else "UNKNOWN"
    ms = re.findall(r"\| (\w+) \| (\d+) \| ([^|]+) \|", text)
    lanes = [{"lane": name, "exit": int(code), "verdict": body.strip()} for name, code, body in ms]
    m2 = re.search(r"generated ([\dT:+-]+Z?)", text)
    generated = m2.group(1) if m2 else ""
    return {
        "version": 1,
        "verdict": verdict,
        "lanes": lanes,
        "lane_count": len(lanes),
        "generated_utc": generated,
        "source": "agent/graphs/auditor_graph.py · docs/evidence/audit-chain.md",
    }


doc = parse()
doc.setdefault("verdict", "UNKNOWN")
doc.setdefault("lanes", [])
doc["emitted_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"audit_chain.json: verdict={doc['verdict']} lanes={len(doc['lanes'])}")
