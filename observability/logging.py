"""Structured JSON logging with job/trace context (C1/C2 observability).

Every service (API, worker, relay) configures this once. Log lines carry
job_id / trace_id when set on the current context, in JSON form — directly
ingestable by Loki/ELK and correlatable with OTel traces.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time

job_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="")
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


class JsonFormatter(logging.Formatter):
    """One-JSON-object-per-line formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        job_id = job_id_var.get()
        trace_id = trace_id_var.get()
        if job_id:
            payload["job_id"] = job_id
        if trace_id:
            payload["trace_id"] = trace_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root handler (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level)
