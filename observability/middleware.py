"""FastAPI middleware for trace context propagation."""


from observability.tracing import _is_enabled


async def add_trace_middleware(app):
    """Attach OpenTelemetry instrumentation to a FastAPI app.

    When OTel is not installed this is a no-op.
    """
    if not _is_enabled():
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass
