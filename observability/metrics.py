"""Minimal in-process Prometheus metrics (C1/C2 observability).

No external registry dependency: counters/gauges live in one process-wide
dict guarded by a lock, rendered in the Prometheus text exposition format
at GET /metrics. Histograms are intentionally out of scope for now — the
goal is an honest, scrapeable baseline that the OTel collector can also
pull later.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_counters: dict[str, float] = {}
_gauges: dict[str, float] = {}
_started_at = time.time()

# 固定直方图桶 (秒), 对齐 PRODUCTION_SPEC §14 性能目标:
# FAST p50<=180s / p95<=480s, DEEP p50<=600s / p95<=1500s。
_HISTOGRAM_BUCKETS: tuple[float, ...] = (
    60.0, 120.0, 180.0, 300.0, 480.0, 600.0, 900.0, 1500.0, 2400.0,
)
# name -> (bucket_ladder, [c_bucket_0, ..., c_bucket_n, c_+Inf, sum, count]).
# The ladder is stored per histogram: the default ladder targets job-level
# durations (minutes), but §14 also sets sub-second targets (GitHub webhook
# p95 <= 1s) whose quantiles are meaningless against 60s bucket resolution —
# an emit site may pass a tighter ladder (see api/server.py middleware).
_histograms: dict[str, tuple[tuple[float, ...], list[float]]] = {}

# ── #184 PR merge outcome counters (court boundary) ──────────────────
# These counters are incremented at the GitHub webhook boundary when a
# pull_request is closed. They represent the court's visibility into the
# final PR disposition: merged vs closed without merge.
PR_MERGED_TOTAL = "pr_merged_total"
PR_CLOSED_WITHOUT_MERGE_TOTAL = "pr_closed_without_merge_total"


def incr(name: str, value: float = 1.0) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0.0) + value


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = value


def observe_duration(
    name: str, seconds: float, buckets: tuple[float, ...] | None = None
) -> None:
    """Record a duration observation into a fixed-bucket histogram.

    Cumulative buckets: every bucket whose upper bound is >= seconds is
    incremented, plus the +Inf bucket, _sum and _count (Prometheus
    exposition semantics). Histograms have no labels (like the rest of
    this hand-rolled registry). ``buckets`` overrides this histogram's
    ladder at first use; later observations reuse the stored ladder
    (a mismatched second call would silently corrupt the cumulative
    counts, so the first one wins by design).
    """
    ladder = _HISTOGRAM_BUCKETS if buckets is None else tuple(buckets)
    with _lock:
        entry = _histograms.get(name)
        if entry is None:
            entry = _histograms[name] = (ladder, [0.0] * (len(ladder) + 3))
        stored_ladder, hist = entry
        for i, upper in enumerate(stored_ladder):
            if seconds <= upper:
                hist[i] += 1.0
        hist[-3] += 1.0  # +Inf bucket
        hist[-2] += seconds  # _sum
        hist[-1] += 1.0  # _count


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "counters": dict(_counters),
            "gauges": dict(_gauges),
            "histograms": {
                name: {
                    "bounds": list(ladder),
                    "buckets": list(hist[:-3]),
                    "inf": hist[-3],
                    "sum": hist[-2],
                    "count": hist[-1],
                }
                for name, (ladder, hist) in _histograms.items()
            },
            "uptime_seconds": time.time() - _started_at,
        }


def render_text() -> str:
    snap = snapshot()
    lines = [
        "# HELP specproof_up Process uptime in seconds.",
        "# TYPE specproof_up gauge",
        f"specproof_up {snap['uptime_seconds']:.1f}",
    ]
    for name, value in sorted(snap["counters"].items()):
        safe = name.replace("-", "_").replace(".", "_")
        lines.append(f"# TYPE specproof_{safe} counter")
        lines.append(f"specproof_{safe} {int(value)}")
    for name, value in sorted(snap["gauges"].items()):
        safe = name.replace("-", "_").replace(".", "_")
        lines.append(f"# TYPE specproof_{safe} gauge")
        lines.append(f"specproof_{safe} {value}")
    for name, hist in sorted(snap["histograms"].items()):
        safe = name.replace("-", "_").replace(".", "_")
        lines.append(f"# HELP specproof_{safe} Duration histogram (seconds).")
        lines.append(f"# TYPE specproof_{safe} histogram")
        bounds: list[float] = hist["bounds"]
        buckets: list[float] = hist["buckets"]
        for i, upper in enumerate(bounds):
            lines.append(
                f'specproof_{safe}_bucket{{le="{upper:g}"}} {int(buckets[i])}'
            )
        lines.append(f'specproof_{safe}_bucket{{le="+Inf"}} {int(hist["inf"])}')
        lines.append(f"specproof_{safe}_sum {hist['sum']}")
        lines.append(f"specproof_{safe}_count {int(hist['count'])}")
    return "\n".join(lines) + "\n"
