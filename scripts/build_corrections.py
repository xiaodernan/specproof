#!/usr/bin/env python
"""build_corrections.py — distil APPENDIX_CORRECTIONS into a compact JSON.

Reads docs/world/APPENDIX_CORRECTIONS.md (zh) + EN sibling and emits
apps/web/src/pages/corrections.json { version, count, items: [{id, summary_zh}] }.
Append-only by construction: this script never edits the source files.
"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "world" / "APPENDIX_CORRECTIONS.md"
OUT = ROOT / "apps" / "web" / "src" / "pages" / "corrections.json"

text = SRC.read_text(encoding="utf-8")
ids = re.findall(r"\| \*\*(R\d+)\*\* \|", text)
items = []
for m in re.finditer(r"\| \*\*[^*]+\*\* \| ([^|]+) \|", text):
    items.append(m.group(1).strip())
doc = {
    "version": 1,
    "source": "docs/world/APPENDIX_CORRECTIONS.md (append-only)",
    "count": len(items),
    "ids": sorted(set(ids), key=lambda s: int(s[1:])),
    "items": items,
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"corrections.json: {len(items)} entries · ids={doc['ids']}")
