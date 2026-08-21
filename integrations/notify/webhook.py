"""Outbound webhook notification connector (first slice).

WebhookConnector delivers a Notification to an incoming-webhook URL with one
of three payload dialects:

- SLACK    Slack-compatible incoming webhook: {"text", "blocks"} (blocks are
           optional and dropped when empty);
- GENERIC  plain JSON of {event_type, title, text, job_id, blocks} with
           optional HMAC-SHA256 signing (X-SpecProof-Signature: sha256=<hex>);
- FEISHU   minimal Feishu-compatible text message: {"msg_type": "text",
           "content": {"text": ...}}.

Secrets live only in the environment: webhook_connector_from_env() reads
SPECPROOF_NOTIFY_WEBHOOK_URL and SPECPROOF_NOTIFY_WEBHOOK_SECRET and nothing
else; the constructor arguments exist so tests can inject fake transports and
secrets without touching the environment. Without a URL the factory returns
the DisabledConnector no-op.

Every body is redacted before it is serialized: contracts.events.redact_secrets
replaces secret-named keys (api_key/token/password/...), then
providers.redaction.redact_text replaces secret-shaped spans (LLM keys,
GitHub tokens, JWTs, ...). The HMAC signs exactly the redacted bytes that go
on the wire, so a signature never vouches for a body that carried a secret.

Failures are classified by providers.resilience.classify_retry (imported, not
reimplemented): 429/500/502/503, timeouts and connection errors retry with
exponential backoff up to max_attempts; 400/401/403/422 and anything
unclassified fail closed after the first attempt. httpx's own exception
classes do not inherit the standard-library TimeoutError/ConnectionError the
matrix recognizes, so the two small twin classes below bridge them. The
retry sleep is injectable so tests never wait.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

import httpx

from contracts.events import redact_secrets
from integrations.notify.protocol import (
    Connector,
    DisabledConnector,
    Notification,
    SendStatus,
)
from providers.redaction import redact_text
from providers.resilience import classify_retry

LOGGER = logging.getLogger("integrations.notify.webhook")

WEBHOOK_URL_ENV = "SPECPROOF_NOTIFY_WEBHOOK_URL"
WEBHOOK_SECRET_ENV = "SPECPROOF_NOTIFY_WEBHOOK_SECRET"
SIGNATURE_HEADER = "X-SpecProof-Signature"
CONTENT_TYPE_HEADER = "Content-Type"
JSON_CONTENT_TYPE = "application/json"

CAPABILITY_TEXT = "text"
CAPABILITY_BLOCKS = "blocks"
CAPABILITY_HMAC = "hmac"

DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 10.0


class WebhookKind(StrEnum):
    """Payload dialect of the target webhook."""

    SLACK = "slack"
    GENERIC = "generic"
    FEISHU = "feishu"


class WebhookTimeoutError(httpx.TimeoutException, TimeoutError):
    """httpx.TimeoutException + builtin TimeoutError twin.

    httpx's TimeoutException does not inherit the standard library
    TimeoutError, but providers.resilience.classify_retry recognizes
    TimeoutError as retryable. Instances of this class are both, so the
    shared classifier sees transport timeouts for what they are without any
    local reimplementation of the retry matrix.
    """


class WebhookConnectionError(httpx.NetworkError, ConnectionError):
    """httpx.NetworkError + builtin ConnectionError twin (same rationale)."""


def hmac_signature(body: bytes, secret: str) -> str:
    """Hex HMAC-SHA256 of body under the configured secret (sha256:<hex>)."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def build_slack_payload(notification: Notification) -> dict[str, Any]:
    """Slack-compatible incoming-webhook JSON: {text, blocks?}."""
    payload: dict[str, Any] = {
        "text": notification.text or notification.title or notification.event_type
    }
    if notification.blocks:
        payload["blocks"] = list(notification.blocks)
    return payload


def build_feishu_payload(notification: Notification) -> dict[str, Any]:
    """Minimal Feishu-compatible text message (msg_type/content only)."""
    text = "\n".join(part for part in (notification.title, notification.text) if part)
    return {"msg_type": "text", "content": {"text": text or notification.event_type}}


def build_generic_payload(notification: Notification) -> dict[str, Any]:
    """Plain JSON notification for generic webhooks (HMAC-friendly)."""
    payload: dict[str, Any] = {
        "event_type": notification.event_type,
        "title": notification.title,
        "text": notification.text,
    }
    if notification.job_id:
        payload["job_id"] = notification.job_id
    if notification.blocks:
        payload["blocks"] = list(notification.blocks)
    return payload


def _payload_for(kind: WebhookKind, notification: Notification) -> dict[str, Any]:
    """Dispatch the payload builder for the connector's dialect."""
    if kind is WebhookKind.SLACK:
        return build_slack_payload(notification)
    if kind is WebhookKind.FEISHU:
        return build_feishu_payload(notification)
    return build_generic_payload(notification)


def _capabilities_for(kind: WebhookKind, secret: str | None) -> frozenset[str]:
    """Feature set advertised for a dialect (+hmac only when signed)."""
    if kind is WebhookKind.SLACK:
        return frozenset({CAPABILITY_TEXT, CAPABILITY_BLOCKS})
    if kind is WebhookKind.FEISHU:
        return frozenset({CAPABILITY_TEXT})
    if secret is not None:
        return frozenset({CAPABILITY_TEXT, CAPABILITY_HMAC})
    return frozenset({CAPABILITY_TEXT})


def _status_from_exception(exc: BaseException) -> int | None:
    """Best-effort HTTP status from a transport exception."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


class WebhookConnector:
    """Send Notifications to an incoming-webhook URL (env-only secrets).

    Constructed instances are always configured (empty URLs are rejected);
    the env-only factory webhook_connector_from_env returns DisabledConnector
    instead when SPECPROOF_NOTIFY_WEBHOOK_URL is absent.
    """

    name: str
    capabilities: frozenset[str]

    def __init__(
        self,
        url: str,
        *,
        kind: WebhookKind = WebhookKind.GENERIC,
        secret: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_backoff: float = DEFAULT_BASE_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        sleep_fn: Callable[[float], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not url.strip():
            raise ValueError("webhook url must not be empty")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        if base_backoff < 0 or max_backoff < base_backoff:
            raise ValueError("backoff must satisfy 0 <= base_backoff <= max_backoff")
        self.url = url
        self.kind = kind
        self.secret = secret if secret else None
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self._sleep_fn: Callable[[float], None] = (
            sleep_fn if sleep_fn is not None else time.sleep
        )
        self._client = httpx.Client(transport=transport, timeout=timeout)
        self.name = "webhook:" + kind.value
        self.capabilities = _capabilities_for(kind, self.secret)
        self.attempts = 0
        self.last_failure_reason: str | None = None

    def close(self) -> None:
        """Release the underlying HTTP client (idempotent)."""
        self._client.close()

    def send(self, notification: Notification) -> SendStatus:
        """Redact, serialize, sign and POST one notification.

        Returns SENT on any response below HTTP 400. Failures are classified
        through providers.resilience.classify_retry (status and/or exception):
        retryable decisions retry with exponential backoff up to max_attempts,
        everything else returns FAILED after the attempt that failed.
        """
        body, headers = self._prepare(notification)
        for attempt in range(1, self.max_attempts + 1):
            self.attempts += 1
            try:
                response = self._client.post(
                    self.url, content=body, headers=headers
                )
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                attempt_exc: BaseException = WebhookTimeoutError(str(exc))
            except httpx.NetworkError as exc:
                attempt_exc = WebhookConnectionError(str(exc))
            except Exception as exc:
                attempt_exc = exc
            else:
                return SendStatus.SENT
            status = _status_from_exception(attempt_exc)
            decision = classify_retry(
                status,
                attempt_exc,
                attempt,
                base_backoff=self.base_backoff,
                max_backoff=self.max_backoff,
                jitter=0.0,
            )
            self.last_failure_reason = decision.reason
            if not decision.retryable or attempt >= self.max_attempts:
                LOGGER.warning(
                    "notification %s failed via %s: %s (status=%s)",
                    notification.event_type,
                    self.name,
                    decision.reason,
                    status,
                )
                return SendStatus.FAILED
            LOGGER.info(
                "notification %s attempt %d failed (%s); retrying in %.1fs",
                notification.event_type,
                attempt,
                decision.reason,
                decision.backoff_seconds,
            )
            self._sleep_fn(decision.backoff_seconds)
        return SendStatus.FAILED

    def _prepare(self, notification: Notification) -> tuple[bytes, dict[str, str]]:
        """Build the redacted, signed wire body (+headers) for one send.

        Redaction happens on the payload dict (secret-named keys) and then on
        the serialized body (secret-shaped spans), BEFORE signing, so the
        HMAC covers exactly the bytes that leave the process.
        """
        safe_payload = redact_secrets(_payload_for(self.kind, notification))
        body_text = json.dumps(safe_payload, ensure_ascii=False)
        body_text, redacted_count = redact_text(body_text)
        if redacted_count:
            LOGGER.info(
                "redacted %d secret-shaped span(s) from notification %s",
                redacted_count,
                notification.event_type,
            )
        body = body_text.encode("utf-8")
        headers = {CONTENT_TYPE_HEADER: JSON_CONTENT_TYPE}
        if self.kind is WebhookKind.GENERIC and self.secret is not None:
            headers[SIGNATURE_HEADER] = hmac_signature(body, self.secret)
        return body, headers


def webhook_connector_from_env(
    kind: WebhookKind = WebhookKind.GENERIC,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_backoff: float = DEFAULT_BASE_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    sleep_fn: Callable[[float], None] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Connector:
    """Build a connector from SPECPROOF_NOTIFY_WEBHOOK_URL/_SECRET (env only).

    No URL -> DisabledConnector, whose send() is a no-op returning DISABLED.
    A secret without a URL is ignored with a warning: nothing is ever sent
    unsigned by accident, because nothing is sent at all.
    """
    url = os.getenv(WEBHOOK_URL_ENV, "").strip()
    secret_raw = os.getenv(WEBHOOK_SECRET_ENV, "").strip()
    if not url:
        if secret_raw:
            LOGGER.warning(
                "%s set but %s missing; notifications disabled",
                WEBHOOK_SECRET_ENV,
                WEBHOOK_URL_ENV,
            )
        return DisabledConnector()
    return WebhookConnector(
        url,
        kind=kind,
        secret=secret_raw or None,
        timeout=timeout,
        max_attempts=max_attempts,
        base_backoff=base_backoff,
        max_backoff=max_backoff,
        sleep_fn=sleep_fn,
        transport=transport,
    )
