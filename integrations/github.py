"""GitHub webhook signature verification (P5).

X-Hub-Signature-256 = HMAC-SHA256(payload, webhook_secret). Verification
is constant-time; failures return 401 and never process the payload.
The webhook secret lives only in the environment (GITHUB_WEBHOOK_SECRET).
"""

from __future__ import annotations

import hashlib
import hmac
import os


class WebhookVerificationError(Exception):
    """Raised when a webhook cannot be verified."""


def verify_signature(
    payload_body: bytes,
    signature_header: str | None,
    secret: str | None = None,
) -> bool:
    """Verify X-Hub-Signature-256 against the shared secret.

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
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, expected)


def sign_payload(payload_body: bytes, secret: str) -> str:
    """Produce the X-Hub-Signature-256 header value (for tests)."""
    digest = hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return "sha256=" + digest
