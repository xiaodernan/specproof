"""OpenTelemetry tracing and W3C Trace Context propagation (P1.7).

When opentelemetry packages are installed, this module initializes a
TracerProvider with OTLP export. Otherwise it degrades to NoOp tracing
so the rest of the system continues to function.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_NOOP = False


def _is_enabled() -> bool:
    """Return True if OpenTelemetry SDK is installed and enabled."""
    if _NOOP:
        return False
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        return False
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


def init_tracing(
    service_name: str = "specproof-p1",
    otlp_endpoint: str | None = None,
) -> Any:
    """Initialize OpenTelemetry SDK with OTLP exporter.

    Args:
        service_name: Service name for the tracer provider.
        otlp_endpoint: OTLP collector endpoint. Defaults to
                       OTEL_EXPORTER_OTLP_ENDPOINT env var or
                       http://localhost:4318/v1/traces.

    Returns:
        A TracerProvider, or None if OTel is not installed.
    """
    if not _is_enabled():
        logger.debug("OpenTelemetry not available; tracing disabled")
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = otlp_endpoint or os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"
        )
        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        logger.info("OpenTelemetry tracing enabled → %s", endpoint)
        return provider
    except Exception as exc:
        logger.warning("Failed to initialize OpenTelemetry: %s", exc)
        return None


@lru_cache(maxsize=1)
def get_tracer(name: str = "specproof") -> Any:
    """Get a tracer instance, or NoOp if OTel is disabled."""
    if _is_enabled():
        try:
            from opentelemetry import trace
            return trace.get_tracer(name)
        except Exception:
            pass
    # Return a no-op tracer
    return _NoOpTracer()


class _NoOpTracer:
    """No-op tracer that implements the same start_as_current_span interface."""

    def start_as_current_span(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return _NoOpSpan()

    def start_span(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return _NoOpSpan()


class _NoOpSpan:
    """No-op span. All operations are silent passthrough."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        pass

    def set_status(self, status: Any, description: str = "") -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def end(self) -> None:
        pass


def inject_trace_context(carrier: dict[str, str]) -> dict[str, str]:
    """Inject W3C Trace Context into a carrier dict (e.g. RabbitMQ headers).

    Returns the carrier with traceparent (and optionally tracestate) added.
    """
    if not _is_enabled():
        return carrier
    try:
        from opentelemetry import propagate
        propagate.inject(carrier)
    except Exception:
        pass
    return carrier


def extract_trace_context(carrier: dict[str, str]) -> Any:
    """Extract W3C Trace Context from a carrier dict.

    Returns a context object that can be passed to attach(), or None.
    """
    if not _is_enabled():
        return None
    try:
        from opentelemetry import propagate
        return propagate.extract(carrier)
    except Exception:
        return None
