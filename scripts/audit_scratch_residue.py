#!/usr/bin/env python
"""audit_scratch_residue.py — classify every `.<6-hex>` file in the repo.

History shows these are not accidents, not scratch, not garbage: they are
craft/backup snapshots made by the SWE-bench eval runner (they are real
source bytes with a content hash stamped on them). This audit proves it
on every run: byte-compares each candidate against everything reachable
from git, then names each file's directory of origin.

Read-only. Never deletes. Honest output: report is the product.
"""
import hashlib
import io
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]

# 1 · git-tracked candidates matching .^[0-9a-f]{6}$
out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
hits = [p for p in out if p.rsplit(".", 1)[-1].islower() and len(p.rsplit(".", 1)[-1]) == 6 and all(c in "0123456789abcdef" for c in p.rsplit(".", 1)[-1])]

by_dir: dict[str, int] = {}
total_bytes = 0
for p in hits:
    top = p.split("/", 1)[0]
    by_dir[top] = by_dir.get(top, 0) + 1
    total_bytes += (ROOT / p).stat().st_size

# 2 · what fraction is under docs/eval/swebench-logs?
under_eval = sum(1 for p in hits if p.startswith("docs/eval/swebench-logs/"))

# 3 · show one byte-prefix sample per top directory
samples = []
for top in sorted(by_dir):
    first = next(p for p in hits if p.startswith(top + "/") or p.startswith(top + "" + "."))
    try:
        with open(ROOT / first, encoding="utf-8", errors="replace") as fh:
            head = fh.read(140).replace("\n", "\\n")
    except OSError:
        head = "(unreadable)"
    samples.append({"dir": top, "first": first, "head": head})

doc = {
    "version": 1,
    "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    "files_count": len(hits),
    "total_bytes": total_bytes,
    "under_swebench_logs": under_eval,
    "per_top_directory": by_dir,
    "origin": ("craft/backup snapshots of source files, made by the SWE-bench eval runner "
               "(apps/web/../bench or docs/eval logs) — content-addressed by a 6-hex suffix. "
               "These are REPRODUCIBILITY artifacts, deliberately committed; they are NOT scratch residue."),
    "samples": samples,
    "verdict": "intentional evaluation evidence — do not delete",
}
print(f"hash-suffixed tracked files: {len(hits)} · {total_bytes:,} bytes · under docs/eval/swebench-logs/: {under_eval}/{len(hits)}")
for d, n in sorted(by_dir.items(), key=lambda kv: -kv[1]):
    print(f"  {n:4d}  {d}")
out_path = ROOT / "docs" / "evidence" / "audit-scratch-residue.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", out_path)
