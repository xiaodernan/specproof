"""Generic notification connectors (first slice, 阶段8/M10).

Integrations that push notifications out of SpecProof — Slack-compatible,
Feishu-compatible and generic HMAC-signed incoming webhooks — plus the
templates that turn persisted job summaries into terminal-event
notifications (VERIFIED / BLOCKED / FAILED / NEEDS_REVIEW).

The package is infrastructure-free: delivery goes through an injectable
httpx transport (tests use fakes), secrets come only from
SPECPROOF_NOTIFY_WEBHOOK_URL / SPECPROOF_NOTIFY_WEBHOOK_SECRET, payloads are
redacted before serialization (contracts.events.redact_secrets +
providers.redaction.redact_text), and retry classification reuses
providers.resilience.classify_retry verbatim.
"""

from integrations.notify.protocol import (
    Connector,
    DisabledConnector,
    Notification,
    SendStatus,
)
from integrations.notify.templates import (
    TERMINAL_VERDICTS,
    blocks_for_summary,
    build_terminal_notification,
    event_type_for_verdict,
    normalize_verdict,
    text_for_summary,
    title_for_verdict,
)
from integrations.notify.webhook import (
    CAPABILITY_BLOCKS,
    CAPABILITY_HMAC,
    CAPABILITY_TEXT,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT,
    SIGNATURE_HEADER,
    WEBHOOK_SECRET_ENV,
    WEBHOOK_URL_ENV,
    WebhookConnectionError,
    WebhookConnector,
    WebhookKind,
    WebhookTimeoutError,
    build_feishu_payload,
    build_generic_payload,
    build_slack_payload,
    hmac_signature,
    webhook_connector_from_env,
)

__all__ = [
    "CAPABILITY_BLOCKS",
    "CAPABILITY_HMAC",
    "CAPABILITY_TEXT",
    "Connector",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_TIMEOUT",
    "DisabledConnector",
    "Notification",
    "SIGNATURE_HEADER",
    "SendStatus",
    "TERMINAL_VERDICTS",
    "WEBHOOK_SECRET_ENV",
    "WEBHOOK_URL_ENV",
    "WebhookConnectionError",
    "WebhookConnector",
    "WebhookKind",
    "WebhookTimeoutError",
    "blocks_for_summary",
    "build_feishu_payload",
    "build_generic_payload",
    "build_slack_payload",
    "build_terminal_notification",
    "event_type_for_verdict",
    "hmac_signature",
    "normalize_verdict",
    "text_for_summary",
    "title_for_verdict",
    "webhook_connector_from_env",
]
