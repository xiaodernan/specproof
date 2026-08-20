"""Unified outbound HTTP helper for providers (§14 统一网络客户端+日志脱敏).

One construction point for the ad-hoc async HTTP clients provider code
uses, plus a redacting formatter: request/response/error summaries pass
through providers.redaction before they reach a log line, so URL
credentials or token-like spans can never leak through provider logging.
"""
from __future__ import annotations

import httpx

from providers.redaction import redact_text

DEFAULT_TIMEOUT = 30.0


def make_async_client(
    timeout: float | None = None,
) -> httpx.AsyncClient:
    """One async client constructor for provider code.

    timeout applies to connect/read/write/pool (httpx semantics). The
    default (30.0s) matches the historical per-check probe timeout.
    """
    effective = DEFAULT_TIMEOUT if timeout is None else timeout
    return httpx.AsyncClient(timeout=effective)


def redact_for_log(text: object, max_len: int = 500) -> str:
    """Redacting formatter: secret-like spans scrubbed, then bounded.

    Returns the redacted string; the returned text is safe to embed in
    log lines. Long payloads are truncated with an ellipsis marker.
    """
    redacted, _count = redact_text(str(text))
    if len(redacted) > max_len:
        return redacted[:max_len] + "\u2026"
    return redacted
