#!/usr/bin/env python
"""Build engine.json — the measured, git-absent LLM ledger of this repository.

Reads `.local/llm_usage.jsonl` (which is git-ignored by design) and emits a
compact summary into `apps/web/src/pages/engine.json` for the in-app `#/engine`
page. The figures this script emits are REAL measured calls made on this
workstation / by this repo's own probe scripts. They are not representative
of any customer's workload, and not representative of the way this repo will
behave in production — but they are true measurements.

Empty file → emits a sensible "no llamas yet" summary with zero counts. That
is fine: it tells the truth about the ledger on this host.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / ".local" / "llm_usage.jsonl"
OUT = ROOT / "apps" / "web" / "src" / "pages" / "engine.json"

rows: list[dict] = []
if LEDGER.exists():
    with open(LEDGER, "rb") as _f:
        raw = _f.read().decode("utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

n = len(rows)
errors = sum(1 for r in rows if r.get("error"))
streamed = sum(1 for r in rows if r.get("streamed") is True)
lanes: dict[str, int] = {}
kinds: dict[str, int] = {}
prompt_total = completion_total = cached_total = cached_basis = 0
durations: list[float] = []
cache_hits_for_display = 0

for r in rows:
    lanes[str(r.get("lane") or "unknown")] = lanes.get(str(r.get("lane") or "unknown"), 0) + 1
    kinds[str(r.get("kind") or "(unspecified)")] = kinds.get(str(r.get("kind") or "(unspecified)"), 0) + 1
    duration = r.get("duration_ms")
    if isinstance(duration, (int, float)) and duration > 0:
        durations.append(float(duration))
    pt = r.get("prompt_tokens")
    ct = r.get("completion_tokens")
    cached = r.get("cached_tokens")
    if isinstance(pt, int):
        prompt_total += pt
    if isinstance(ct, int):
        completion_total += ct
    if isinstance(cached, int):
        cached_total += cached
        cached_basis += 1  # only tally a call when it reported a count

durations_sorted = sorted(durations) if durations else []
def pct(p: float) -> int | None:
    if not durations_sorted:
        return None
    idx = max(0, min(len(durations_sorted) - 1, int(round((p / 100) * (len(durations_sorted) - 1)))))
    return int(durations_sorted[idx])

# Hourly buckets — last 30h from last call backwards
hour_buckets: dict[str, dict[str, int]] = {}
for r in rows:
    ts = r.get("ts")
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        continue
    hour = dt.strftime("%Y-%m-%dT%H:00Z")
    b = hour_buckets.setdefault(hour, {"calls": 0, "prompt_tokens": 0, "cached_tokens": 0})
    b["calls"] += 1
    if isinstance(r.get("prompt_tokens"), int):
        b["prompt_tokens"] += r["prompt_tokens"]
    if isinstance(r.get("cached_tokens"), int):
        b["cached_tokens"] += r["cached_tokens"]

# pick most recent 24 hours by key
ordered_keys = sorted(hour_buckets.keys())[-28:]
series = [hour_buckets[k] for k in ordered_keys]
calls_max = max([s["calls"] for s in series] + [1])

data = {
    "version": 1,
    "source": ".local/llm_usage.jsonl (untracked; this host only)",
    "calls": n,
    "errors": errors,
    "streamed_ratio": (streamed / n) if n else None,
    "prompt_tokens": prompt_total,
    "completion_tokens": completion_total,
    "cached_tokens": cached_total,
    "cached_basis": cached_basis,
    "cache_hit_rate": (cached_total / prompt_total) if prompt_total else None,
    "latency_p50_ms": pct(50),
    "latency_p95_ms": pct(95),
    "latency_max_ms": int(max(durations)) if durations else None,
    "lanes": dict(sorted(lanes.items(), key=lambda kv: -kv[1])),
    "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
    "hourly_30": series,
    "hourly_30_max_calls": calls_max,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", encoding="utf-8") as _f:
    _f.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
print(f"wrote {OUT}")
print(f"calls={n} errors={errors} streamed_ratio={data['streamed_ratio']}")
print(f"tokens prompt={prompt_total} completion={completion_total} cached={cached_total} (measured on {cached_basis} of {n} calls)")
print(f"latency p50={data['latency_p50_ms']} p95={data['latency_p95_ms']} max={data['latency_max_ms']}")
print(f"lanes={data['lanes']}  kinds={data['kinds']}  hours_covered={len(series)}")
