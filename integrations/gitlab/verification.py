"""GitLab webhook token verification.

GitLab does not sign webhook bodies. Instead, the hook is configured with a
shared secret token that GitLab sends verbatim in the X-Gitlab-Token header.
The header value is compared against the configured token with
hmac.compare_digest, so the comparison is constant-time (timing-safe) and
verification fails closed when no token is configured (GITLAB_WEBHOOK_TOKEN).

The token must live only in the environment — never in source, config
files, or logs (see tests/security/test_no_key_leak.py).
"""

from __future__ import annotations

import os
from hmac import compare_digest

GITLAB_WEBHOOK_TOKEN = "GITLAB_WEBHOOK_TOKEN"


class WebhookVerificationError(Exception):
    """Raised when the webhook cannot be verified (fail-closed)."""


def verify_token(token_header: str | None, secret: str | None = None) -> bool:
    """Compare the X-Gitlab-Token header against the configured secret.

    Returns True when the tokens match (timing-safe). Returns False for a
    missing or mismatched header value. Raises WebhookVerificationError when
    no secret is configured — never returns True in that case.
    """
    if secret is None:
        secret = os.getenv(GITLAB_WEBHOOK_TOKEN, "")
    if not secret:
        raise WebhookVerificationError(
            f"{GITLAB_WEBHOOK_TOKEN} not configured — refusing webhook"
        )
    if not token_header:
        return False
    return compare_digest(token_header.encode("utf-8"), secret.encode("utf-8"))
