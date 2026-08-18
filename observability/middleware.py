"""FastAPI middleware for trace context propagation."""
from typing import Any

from observability.tracing import _is_enabled


def add_trace_middleware(app: Any) -> None:
    """Attach OpenTelemetry instrumentation to a FastAPI app (sync).

    When OTel is not installed/enabled this is a no-op.
    """
    if not _is_enabled():
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass
