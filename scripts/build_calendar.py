#!/usr/bin/env python
"""Build calendarData.json — one year of real commit activity, derived from git.

Counts `git log --since=<1 year ago>` per calendar day (author-date, short
format) and writes the result as a compact JSON consumed by the `#/calendar`
route. Read-only with respect to git; nothing is extrapolated or smoothed.

Output: apps/web/src/pages/calendarData.json
"""

import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "apps" / "web" / "src" / "pages" / "calendarData.json"

STAT_CMD = ["git", "log", "--since=1 year ago", "--format=%ad", "--date=short"]

def main() -> int:
    raw = subprocess.check_output(STAT_CMD, cwd=REPO).decode("utf-8", errors="ignore")
    counts = Counter(line.strip() for line in raw.splitlines() if line.strip())
    if not counts:
        print("git log returned no commits — refusing to write an empty calendar", file=sys.stderr)
        return 2

    today = date.today()
    year_ago = today - timedelta(days=364)  # label: the last 365 days inclusive
    daily = {(today - timedelta(days=offset)).isoformat(): 0 for offset in range(365)}
    for day, n in counts.items():
        if day in daily:
            daily[day] = n

    busiest_date, busiest_count = max(daily.items(), key=lambda kv: kv[1])
    total = sum(daily.values())
    busiest_streak = 0
    run = 0
    for day in sorted(daily):
        if daily[day] > 0:
            run += 1
            busiest_streak = max(busiest_streak, run)
        else:
            run = 0

    stats = {
        "generated_by": "scripts/build_calendar.py",
        "since": year_ago.isoformat(),
        "until": today.isoformat(),
        "total_commits": total,
        "busiest_date": busiest_date,
        "busiest_count": busiest_count,
        "longest_streak": busiest_streak,
        "days": daily,
    }
    OUT.write_text(json.dumps(stats, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8", newline="\n")
    print(f"since: {year_ago}  until: {today}")
    print(f"commits in window: {total}")
    print(f"busiest day: {busiest_date} ({busiest_count} commits)")
    print(f"longest streak: {busiest_streak} days")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
