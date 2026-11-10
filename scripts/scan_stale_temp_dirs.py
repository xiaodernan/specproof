#!/usr/bin/env python3
"""Read-only census of stale specproof-* temp directories.

Why this script exists
----------------------
The product's own tooling (scratch worktrees, MCP verify runs, batch replay,
drill harnesses) drops directories into the host's temp root and historically
nobody counted them — the 2026-11-09 baseline found 325 matching directories,
297 marked stale, with a handful of paths still alive (see the ledger entry
for that number). The maintenance scan that only existed as a one-off probe is
now a first-class, read-only fact-finder.

What it does NOT do
-------------------
It does not delete, move, rename, or touch anything — not the directories,
not the repo's `.git/worktrees` admin entries, not a single byte. Deletion is
a human decision with an explicit blast radius; this script only answers
"what is here, and how old is it?"

Output: a table per family (count / age buckets / oldest / newest), the
`.git/worktrees` admin entries and which of them dangle (the admin entry
points at a path that no longer exists), and, with --json, the same records
machine-readable. Use --bytes to also measure shallow sizes (slow — walks
every matching directory; bounded by entering only what matches).

Exit codes: 0 — scan completed; 2 — usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from contextlib import suppress
from pathlib import Path

#: Families the leak has been seen in. The list is deliberately closed;
#: unknown top-level `specproof-*` names are reported separately so a new
#: prefix cannot slip in silently.
KNOWN_PREFIXES = (
    "specproof-base-",
    "specproof-head-",
    "specproof-mcp-verify-",
    "specproof-mcp-craft-",
    "specproof-batch-replay-",
    "specproof-replay-",
    "specproof-drill-",
)

#: Age buckets in days. `1-7d` matches the age of a typical CI cycle.
AGE_BUCKETS = ((1, "<1d"), (7, "1-7d"), (30, "7-30d"))


def age_seconds(mtime: float, now: float) -> float:
    return now - mtime


def age_bucket(age_seconds_value: float) -> str:
    days = age_seconds_value / 86400
    for limit, label in AGE_BUCKETS:
        if days < limit:
            return label
    return ">30d"


def scan(temp_root: Path, *, measure_bytes: bool = False) -> dict:
    """Census every matching directory under ``temp_root`` (read-only)."""
    now = time.time()
    by_prefix: Counter[str] = Counter()
    foreign: list[str] = []
    age_buckets: Counter[str] = Counter()
    rows: list[dict] = []
    oldest: tuple[float, str] | None = None
    newest: tuple[float, str] | None = None

    if not temp_root.is_dir():
        return {"error": f"temp root {temp_root} is not a directory", "families": [], "foreign": []}

    for entry in temp_root.iterdir():
        if not entry.is_dir():
            continue
        matched = next((p for p in KNOWN_PREFIXES if entry.name.startswith(p)), None)
        if matched is None:
            if entry.name.startswith("specproof-"):
                foreign.append(entry.name)
            continue
        by_prefix[matched] += 1

    for prefix in KNOWN_PREFIXES:
        total_bytes = 0
        for entry in temp_root.glob(prefix + "*"):
            if not entry.is_dir():
                continue
            try:
                st = entry.stat()
            except OSError:
                age_buckets["unknown"] += 1
                continue
            age = age_seconds(st.st_mtime, now)
            age_buckets[age_bucket(age)] += 1
            if oldest is None or st.st_mtime < oldest[0]:
                oldest = (st.st_mtime, entry.name)
            if newest is None or st.st_mtime > newest[0]:
                newest = (st.st_mtime, entry.name)
            if measure_bytes:
                total_bytes += shallow_size(entry)
        rows.append({"prefix": prefix, "count": by_prefix[prefix], "bytes": total_bytes})

    return {
        "temp_root": str(temp_root),
        "families": sorted(rows, key=lambda r: (-r["count"], r["prefix"])),
        "total_dirs": sum(by_prefix.values()),
        "age_buckets": dict(age_buckets),
        "foreign": sorted(foreign),
        "oldest": (
            {"name": oldest[1], "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(oldest[0]))}
            if oldest else None
        ),
        "newest": (
            {"name": newest[1], "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(newest[0]))}
            if newest else None
        ),
    }


def shallow_size(path: Path) -> int:
    """First-level size only — a full walk of hundreds of trees is not the point."""
    total = 0
    try:
        for entry in path.iterdir():
            if entry.is_file():
                with suppress(OSError):
                    total += entry.stat().st_size
    except OSError:
        pass
    return total


def worktree_admin_entries(repo_dir: Path) -> list[dict]:
    """Read ``.git/worktrees/*`` and report the recorded target path.

    A stale admin entry is one whose recorded path no longer exists. This
    function only reads — it does not claim which is stale nor prune anything.
    """
    wt_root = repo_dir / ".git" / "worktrees"
    entries: list[dict] = []
    if not wt_root.is_dir():
        return entries
    for admin in sorted(wt_root.iterdir()):
        if not admin.is_dir():
            continue
        gitdir_file = admin / "gitdir"
        target = None
        exists = None
        try:
            target = gitdir_file.read_text(encoding="utf-8", errors="replace").strip()
            exists = Path(target).is_absolute() and Path(target).exists()
        except OSError:
            pass
        entries.append({"admin": admin.name, "target": target, "target_exists": exists})
    return entries


def _render_table(report: dict) -> str:
    lines = ["=== specproof-* temp census (read-only) ==="]
    lines.append(f"temp root: {report['temp_root']}")
    lines.append("")
    lines.append("family                        count      bytes")
    for row in report["families"]:
        b = f"{row['bytes'] / 1024:.0f} KiB" if row["bytes"] else "n/a"
        lines.append(f"{row['prefix']:28} {row['count']:5}   {b}")
    lines.append(f"\nTOTAL dirs = {report['total_dirs']}")
    if report["age_buckets"]:
        lines.append("")
        lines.append("age buckets (mtime):")
        for bucket in ("<1d", "1-7d", "7-30d", ">30d", "unknown"):
            if bucket in report["age_buckets"]:
                lines.append(f"  {bucket:8} {report['age_buckets'][bucket]}")
    if report.get("foreign"):
        lines.append("")
        lines.append("foreign specproof-* prefixes (not in the closed list):")
        for name in report["foreign"]:
            lines.append(f"  {name}")
    if report.get("oldest"):
        lines.append(f"\noldest: {report['oldest']['when']} {report['oldest']['name']}")
    if report.get("newest"):
        lines.append(f"newest: {report['newest']['when']} {report['newest']['name']}")
    return "\n".join(lines)


def _render_worktree(repo_dir: Path) -> str:
    lines = ["=== .git/worktrees admin entries ==="]
    entries = worktree_admin_entries(repo_dir)
    if not entries:
        lines.append("(no admin entries)")
        return "\n".join(lines)
    lines.append(f"count = {len(entries)}")
    for e in entries:
        flag = "  [dangling]" if e["target_exists"] is False else ""
        lines.append(f"  {e['admin']:28} -> {e['target']}{flag}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_temp = (
        os.environ.get("TEMP")
        or os.environ.get("TMP")
        or r"C:\Users\18414\AppData\Local\Temp"
    )
    parser.add_argument("--temp-root", default=default_temp)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--bytes", action="store_true", help="also measure shallow sizes (slow)")
    parser.add_argument("--admin-only", action="store_true", help="only the .git/worktrees census")
    args = parser.parse_args(argv)

    repo_dir = Path(args.repo)
    if args.admin_only:
        entries = worktree_admin_entries(repo_dir)
        if args.json:
            print(json.dumps(entries, indent=2))
        else:
            print(_render_worktree(repo_dir))
        return 0

    report = scan(Path(args.temp_root), measure_bytes=args.bytes)
    if "error" in report:
        print(report["error"], file=sys.stderr)
        return 2
    report["worktree_admin"] = worktree_admin_entries(repo_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_render_table(report))
        print()
        print(_render_worktree(repo_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
