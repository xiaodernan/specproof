"""Cross-service contracts: the §3.4 event Envelope and its helpers.

The event envelope is the single wire contract between the API/relay
(producer) and workers/integrations (consumers). See contracts/events.py.
"""

from contracts.events import (  # noqa: F401
    DEFAULT_ACTOR_ID,
    DEFAULT_AGGREGATE_TYPE,
    DEFAULT_TENANT_ID,
    REDACTION_PLACEHOLDER,
    SCHEMA_VERSION,
    build_envelope,
    payload_digest,
    redact_secrets,
)

__all__ = [
    "DEFAULT_ACTOR_ID",
    "DEFAULT_AGGREGATE_TYPE",
    "DEFAULT_TENANT_ID",
    "REDACTION_PLACEHOLDER",
    "SCHEMA_VERSION",
    "build_envelope",
    "payload_digest",
    "redact_secrets",
]
