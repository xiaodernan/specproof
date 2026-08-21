"""Event Envelope contract for cross-service events (guide §3.4).

Canonical envelope — every field present on every event:

    event_id, event_type, occurred_at, tenant_id, actor_id, trace_id,
    aggregate_type, aggregate_id, schema_version, idempotency_key,
    payload, payload_digest

Safety invariants (§3.4): event content must never carry plaintext API
keys, private keys or unmasked model requests. build_envelope therefore
redacts known secret-named fields from the payload BEFORE computing the
digest, so payload_digest always covers exactly what goes on the wire.
Over-redaction (a false positive match on a key name) is intentional and
fail-safe: it can never leak a secret.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_TENANT_ID = "default"
DEFAULT_ACTOR_ID = "system"
DEFAULT_AGGREGATE_TYPE = "verification_job"
REDACTION_PLACEHOLDER = "[REDACTED]"

#: Key names that always get redacted inside event payloads (§3.4).
#: Matching is substring-based and case-insensitive so variants like
#: x-api-key or ACCESS_TOKEN are caught; over-matching only hides data.
_SECRET_KEY_RE = re.compile(
    r"api[_-]?key|apikey|access[_-]?token|token|secret|password|passwd|"
    r"private[_-]?key|authorization|credential",
    re.IGNORECASE,
)


def _now_iso() -> str:
    """UTC timestamp with millisecond precision, Z suffix (guide format)."""
    return (
        datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def payload_digest(payload: dict[str, Any]) -> str:
    """Deterministic sha256 digest of a payload dictionary.

    Key order, whitespace and unicode escapes are normalized, so two
    logically equal payloads always produce the same digest.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, default=str,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def redact_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of payload with secret-named fields replaced.

    Recursive: nested dictionaries and lists are redacted in place of the
    copy, everything else is passed through unchanged.
    """
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(key, str) and _SECRET_KEY_RE.search(key):
            redacted[key] = REDACTION_PLACEHOLDER
        elif isinstance(value, dict):
            redacted[key] = redact_secrets(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_secrets(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted


def build_envelope(
    event_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
    occurred_at: str | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    actor_id: str = DEFAULT_ACTOR_ID,
    trace_id: str = "",
    aggregate_type: str = DEFAULT_AGGREGATE_TYPE,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Build the canonical §3.4 event envelope.

    event_id defaults to a fresh uuid4 hex string (32 lowercase hex chars)
    and occurred_at to the current UTC time; both can be pinned by the
    caller for replay/determinism. The payload is secret-redacted before
    it is embedded or digested.
    """
    safe_payload = redact_secrets(payload)
    return {
        "event_id": event_id if event_id is not None else uuid.uuid4().hex,
        "event_type": event_type,
        "occurred_at": occurred_at if occurred_at is not None else _now_iso(),
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "trace_id": trace_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "schema_version": SCHEMA_VERSION,
        "idempotency_key": idempotency_key,
        "payload": safe_payload,
        "payload_digest": payload_digest(safe_payload),
    }
