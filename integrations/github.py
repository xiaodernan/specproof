"""GitHub webhook signature verification (P5).

X-Hub-Signature-256 = HMAC-SHA256(payload, webhook_secret). Verification
is constant-time; failures return 401 and never process the payload.
The webhook secret lives only in the environment (GITHUB_WEBHOOK_SECRET).

Optional signed timestamps (Slack-style): when a sender attaches an
X-Signature-Timestamp header, the HMAC must cover b"v0:" + timestamp +
b":" + payload instead of the bare payload, so the replay window cannot
be circumvented by forging a fresh timestamp. GitHub itself never sends the
header, so the body-only scheme remains the GitHub wire format.
"""

from __future__ import annotations

import hashlib
import hmac
import os


class WebhookVerificationError(Exception):
    """Raised when a webhook cannot be verified."""


def _signing_payload(payload_body: bytes, timestamp: str | None) -> bytes:
    """Bytes the HMAC must cover: bare body, or v0:timestamp:body."""
    if timestamp is None:
        return payload_body
    return b"v0:" + timestamp.encode() + b":" + payload_body


def verify_signature(
    payload_body: bytes,
    signature_header: str | None,
    secret: str | None = None,
    timestamp: str | None = None,
) -> bool:
    """Verify X-Hub-Signature-256 against the shared secret.

    With timestamp None (the GitHub wire format) the HMAC covers the bare
    body. When a sender attaches X-Signature-Timestamp the HMAC must cover
    b"v0:" + timestamp + b":" + body, so a replayed signature cannot be
    refreshed with a forged timestamp.

    Returns True when the signature is valid. Raises
    WebhookVerificationError for configuration problems (missing secret)
    — never returns True in that case (fail-closed).
    """
    secret = secret or os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        raise WebhookVerificationError(
            "GITHUB_WEBHOOK_SECRET not configured — refusing webhook"
        )
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[len("sha256="):]
    computed = hmac.new(
        secret.encode(), _signing_payload(payload_body, timestamp), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, expected)


def sign_payload(payload_body: bytes, secret: str) -> str:
    """Produce the X-Hub-Signature-256 header value (for tests)."""
    digest = hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return "sha256=" + digest


def sign_payload_with_timestamp(
    payload_body: bytes, timestamp: str, secret: str
) -> str:
    """Produce a signature covering a signed timestamp (for tests)."""
    digest = hmac.new(
        secret.encode(), _signing_payload(payload_body, timestamp), hashlib.sha256
    ).hexdigest()
    return "sha256=" + digest
