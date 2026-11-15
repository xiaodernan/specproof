#!/usr/bin/env python
"""Build inkwell.json — how this repository writes itself.

Reads `git log` (author date, with offset) and emits a compact portrait:
counts, spans, streaks, quiet spells, hour-of-day and prefix histograms.
No author names or addresses are ever emitted — this page is about the
repository's rhythm, never about who wrote which line.
"""
import io, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps" / "web" / "src" / "pages" / "inkwell.json"

out = subprocess.run(
    ["git", "log", "--format=%aI|%s", "--reverse"],
    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
)
rows = []
for raw in out.stdout.splitlines():
    if "|" not in raw:
        continue
    when, subject = raw.split("|", 1)
    try:
        dt = datetime.fromisoformat(when)
    except ValueError:
        continue
    rows.append((dt, subject))

if not rows:
    print("no commits found")
    raise SystemExit(1)

total = len(rows)
first = rows[0][0]
last = rows[-1][0]

# local-hour histogram (committer's own clock, from the offset)
hours = [0] * 24
weekdays = [0] * 7
for dt, _ in rows:
    hours[dt.hour] += 1
    weekdays[dt.weekday()] += 1

# weekly buckets, last 52 weeks ending at the last commit
last_naive = last.date()
weeks = []
for w in range(51, -1, -1):
    start_end = last_naive - timedelta(days=(w + 1) * 7 - 1)
    start = last_naive - timedelta(days=(w + 1) * 7 - 1)
    end = last_naive - timedelta(days=w * 7)
    lo = datetime(start.year, start.month, start.day, tzinfo=first.tzinfo)
    hi = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=first.tzinfo)
    weeks.append(sum(1 for dt, _ in rows if lo <= dt <= hi))
assert sum(weeks) <= total

# streaks over calendar days (committer-local)
day_set = sorted({dt.date() for dt, _ in rows})
streak = best_streak = 1
for prev, curr in zip(day_set, day_set[1:]):
    if (curr - prev).days == 1:
        streak += 1
        best_streak = max(best_streak, streak)
    elif (curr - prev).days > 1:
        streak = 1

# longest quiet gap between consecutive commits (hours)
quiet = 0.0
for a, b in zip(rows, rows[1:]):
    quiet = max(quiet, (b[0] - a[0]).total_seconds())
quiet_days = round(quiet / 86400, 1)

# conventional-commit prefix histogram (top 10)
prefix_re = re.compile(r"^([a-z]+)(\([^)]*\))?!?:")
prefix_counts: dict[str, int] = {}
for _, subject in rows:
    m = prefix_re.match(subject)
    key = m.group(1) if m else "(other)"
    prefix_counts[key] = prefix_counts.get(key, 0) + 1
prefixes = dict(sorted(prefix_counts.items(), key=lambda kv: (-kv[1], kv[0])))
prefixes = dict(list(prefixes.items())[:12])

data = {
    "version": 1,
    "commits": total,
    "first": first.isoformat(),
    "last": last.isoformat(),
    "span_days": (last.date() - first.date()).days,
    "hours_local": hours,
    "weekdays": weekdays,
    "weeks52": weeks,
    "longest_day_streak": best_streak,
    "longest_quiet_days": quiet_days,
    "prefixes": prefixes,
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", OUT)
print("total", total, "| span_days", data["span_days"], "| streak", best_streak, "| quiet_days", quiet_days)
print("prefixes", prefixes)
print("sum(hours)", sum(hours), "sum(weekdays)", sum(weekdays), "sum(weeks52)", sum(weeks))
