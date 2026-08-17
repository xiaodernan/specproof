"""Back-compat re-export of the metrics registry (now observability.metrics).

The registry moved to the observability package so the worker and the
outbox relay can emit gauges/counters without importing the API layer.
"""
from observability.metrics import (  # noqa: F401
    incr,
    render_text,
    set_gauge,
    snapshot,
)

__all__ = ["incr", "render_text", "set_gauge", "snapshot"]
