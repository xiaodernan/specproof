#!/usr/bin/env python
"""Build chronicle.json — the machine-readable "SpecProof exists" digestion.

Walks the append-only ledger (docs/operations/DEEP_OPTIMIZATION_PLAN.md),
extracts every `## #NNNN Title` heading plus a one-line summary of its body,
and writes a small JSON payload consumed by the `#/chronicle` route.

Two honest points:

1. This is **read-only** with respect to the ledger. If the ledger is wrong,
   this script surfaces the wrong; it does not correct it.
2. Regenerating **changes the output that goes to the browser**. That is the
   point — the page stays truthful only if the JSON is rebuilt after a ledger
   append. The rebuild path is: `python scripts/build_chronicle.py`, and the
   resulting `apps/web/src/pages/chronicle.json` is checked in.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md"
OUT = REPO / "apps" / "web" / "src" / "pages" / "chronicle.json"

_ENTRY_RE = re.compile(r"^## (#\d+)\s+(.+?)\s*$", re.M)


def main() -> int:
    if not LEDGER.is_file():
        print(f"ledger not found at {LEDGER}", file=sys.stderr)
        return 2

    text = LEDGER.read_text(encoding="utf-8")
    matches = list(_ENTRY_RE.finditer(text))
    print(f"sections found: {len(matches)}")

    entries = []
    for idx, m in enumerate(matches):
        number = int(m.group(1)[1:])
        title = m.group(2).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        first_meaningful = ""
        for ln in body.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("**") and not ln.startswith("---") and not ln.startswith("|"):
                first_meaningful = ln
                break
        entries.append({
            "n": number,
            "t": title,
            "s": first_meaningful[:220],
        })

    entries.sort(key=lambda e: e["n"])
    OUT.write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )
    print(f"first: #{entries[0]['n']} {entries[0]['t'][:70]}")
    print(f"last:  #{entries[-1]['n']} {entries[-1]['t'][:70]}")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.1f} KB, {len(entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
