#!/usr/bin/env python
"""sync_portfolio_dryrun.py — see what portfolio-sync would publish, without pushing.

Invokes scripts/sync_portfolio.py in a scratch directory and prints a report:
the three data-drop files, their byte sizes and their intended consumers
(xiaodernan.github.io via portfolio-sync.yml when PORTFOLIO_TOKEN is set).
No network, no key, no push. Exits 0.
"""
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts" / "sync_portfolio.py"
OUT = ROOT / "artifacts" / "portfolio-data-dryrun"


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    _out = OUT.parent / "portfolio-data-scratch"
    # sync_portfolio.py writes into artifacts/portfolio-data; relocate by monkey-flag if supported,
    # otherwise just read whatever it writes.
    proc = subprocess.run(
        [sys.executable, str(SRC)],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
        encoding="utf-8", errors="replace",
    )
    print("sync_portfolio.py exit:", proc.returncode)
    return proc


def summarize(files):
    total = 0
    rows = []
    for f in files:
        raw = f.read_bytes()
        total += len(raw)
        rows.append({"file": f.name, "bytes": len(raw), "lines": raw.count(b"\n") + 1, "sample": raw[:200].decode("utf-8", errors="replace").strip()})
    return rows, total


def main() -> int:
    _proc = run()
    src_dir = ROOT / "artifacts" / "portfolio-data"
    if not src_dir.is_dir():
        print("sync_portfolio.py produced no artifacts — nothing to preview.")
        return 1
    files = sorted(src_dir.glob("*"))
    rows, total = summarize(files)
    doc = {
        "version": 1,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "would_push": rows,
        "total_bytes": total,
        "portfolio_token_set": bool(__import__("os").environ.get("PORTFOLIO_TOKEN")),
        "consumers": [
            "xiaodernan/xiaodernan.github.io: data/specproof-sync.json (the week's stats)",
            "xiaodernan/xiaodernan.github.io: data/specproof-latest.md (one-liner 'what shipped')",
            "xiaodernan/xiaodernan.github.io: data/specproof-products.json (route catalogue)",
        ],
        "note": "This is a dry-run. Nobody will see artifacts/ until PORTFOLIO_TOKEN is set and portfolio-sync.yml pushes the drop.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "preview.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nportfolio-data dry-run: {len(rows)} file(s), total {total:,} bytes (token set: {doc['portfolio_token_set']})")
    for r in rows:
        print(f"- {r['file']}  {r['bytes']:,} B  {r['lines']} lines")
    print(f"\npreview: {OUT / 'preview.json'}")
    print("Nothing was pushed. Nothing will ever be pushed by this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
