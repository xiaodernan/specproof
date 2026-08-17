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


def incr(name: str, value: float = 1.0) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0.0) + value


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = value


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "counters": dict(_counters),
            "gauges": dict(_gauges),
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
    return "\n".join(lines) + "\n"
