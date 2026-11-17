#!/usr/bin/env python3
"""Build ``docs/latest.json`` — the live fact pack for the portfolio card.

The showcase (xiaodernan.github.io) fetches this file raw from master and
renders the SpecProof strip with the same discipline every other flagship
uses: only numbers that THIS repo can derive from itself are confessed.

Honest sourcing, in order of preference:

* ``exhibits_count`` — read from ``apps/web/src/pages/evidence.json``
  (the evidence pipeline itself produces that file; never re-typed by hand);
* ``total_commits`` / ``tracked_files`` / ``head`` — git, right now;
* ``worldbook_scrolls`` — count of top-level ``## `` chapters in the zh
  world book (mirror files must agree; if they drift the job fails loudly);
* ``chronicle_entries`` — the ledger's own ``## #NNNN`` headings, parsed
  exactly as ``scripts/build_chronicle.py`` parses them;
* ``latest_strike`` — the ``#NNNN`` tag on this commit's subject, if any.

Nothing here is invented, hard-coded or copied from a previous print run.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
WORLD_ZH = ROOT / "docs" / "world" / "SPECROOF_WORLD.md"
WORLD_EN = ROOT / "docs" / "world" / "EN" / "SPECROOF_WORLD_EN.md"
LEDGER = ROOT / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md"
EVIDENCE = ROOT / "apps" / "web" / "src" / "pages" / "evidence.json"
OUT = ROOT / "docs" / "latest.json"


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=True, timeout=120,
    )
    return proc.stdout.strip()


def main() -> int:
    head = _git("rev-parse", "--short", "HEAD")
    total_commits = int(_git("rev-list", "--count", "HEAD"))
    tracked_files = sum(1 for line in _git("ls-files").splitlines() if line.strip())

    scrolls_zh = len(re.findall(r"(?m)^##\s", WORLD_ZH.read_text(encoding="utf-8")))
    scrolls_en = len(re.findall(r"(?m)^##\s", WORLD_EN.read_text(encoding="utf-8")))
    if scrolls_zh != scrolls_en:
        print(f"worldbook drift: zh={scrolls_zh} en={scrolls_en} — refusing to emit a lie", file=sys.stderr)
        return 1
    # the page's worldbook counts every ## chapter plus the frontispiece
    scrolls_zh += 1

    chronicle_entries = len(re.findall(r"(?m)^## (#\d+)\s+", LEDGER.read_text(encoding="utf-8")))

    exhibits_count = None
    if EVIDENCE.is_file():
        try:
            exhibits_count = int(json.loads(EVIDENCE.read_text(encoding="utf-8")).get("exhibits_count") or 0) or None
        except Exception:
            exhibits_count = None

    subject = _git("log", "-1", "--pretty=%s")
    match = re.search(r"#(\d{4})", subject)
    latest_strike = f"#{match.group(1)}" if match else None

    # Self-check: anything resembling a degenerate strike (shallow clone,
    # partial history, transient mis-read) must be refused — never emit a
    # fact pack that contradicts the world the ledger knows. The thresholds
    # are deliberately conservative (this world struck 2661 commits by now);
    # a smaller count is a bug, not a fact.
    if total_commits < 100:
        print(f"degenerate fact pack: total_commits={total_commits} (<100) — shallow clone or stripped history; refusing to emit", file=sys.stderr)
        return 1
    if scrolls_zh < 100:
        print(f"degenerate fact pack: worldbook_scrolls={scrolls_zh} (<100) — watch guard misfire; refusing to emit", file=sys.stderr)
        return 1
    if chronicle_entries < 1000:
        print(f"degenerate fact pack: chronicle_entries={chronicle_entries} (<1000) — ledger read misfired; refusing to emit", file=sys.stderr)
        return 1

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "head": head,
        "total_commits": total_commits,
        "tracked_files": tracked_files,
        "worldbook_scrolls": scrolls_zh,
        "chronicle_entries": chronicle_entries,
        "exhibit_entries": exhibits_count,
        "latest_strike": latest_strike,
        "note": "machine-struck from this repo; not an editorial statement",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} (head {head} · {total_commits} commits · {tracked_files} tracked files · {scrolls_zh} scrolls · {chronicle_entries} chronicle entries · {exhibits_count} exhibits · strike {latest_strike})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
