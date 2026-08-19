"""GitLab webhook + merge request integration (first slice).

Covers the dry, infrastructure-free pieces of the GitLab MR flow:

- X-Gitlab-Token verification (timing-safe, fail-closed),
- Merge Request Hook parsing (opened/updated with source/target branch
  and project id),
- delivery-id idempotency (X-Gitlab-Event-UUID) reusing the outbox
  envelope idempotency-key convention,
- a dry connector that maps MR events to verify-job creation requests
  through an injected job-creator callable (no live API wiring).
"""

from integrations.gitlab.connector import (
    ACTION_DUPLICATE_DELIVERY,
    ACTION_IGNORED,
    ACTION_JOB_CREATED,
    DELIVERY_HEADER,
    EVENT_HEADER,
    MERGE_REQUEST_HOOK,
    TOKEN_HEADER,
    ConnectorResult,
    DeliveryRegistry,
    GitLabMRConnector,
    JobCreator,
    VerifyJobRequest,
    WebhookAuthenticationError,
    delivery_key,
    map_event_to_job_request,
    outbox_idempotency_key,
    process_webhook,
)
from integrations.gitlab.events import (
    ACTIONABLE_MERGE_REQUEST_ACTIONS,
    EventParseError,
    MergeRequestEvent,
    parse_merge_request_event,
)
from integrations.gitlab.verification import (
    GITLAB_WEBHOOK_TOKEN,
    WebhookVerificationError,
    verify_token,
)

__all__ = [
    "ACTION_DUPLICATE_DELIVERY",
    "ACTION_IGNORED",
    "ACTION_JOB_CREATED",
    "ACTIONABLE_MERGE_REQUEST_ACTIONS",
    "ConnectorResult",
    "DELIVERY_HEADER",
    "DeliveryRegistry",
    "EVENT_HEADER",
    "EventParseError",
    "GITLAB_WEBHOOK_TOKEN",
    "GitLabMRConnector",
    "JobCreator",
    "MERGE_REQUEST_HOOK",
    "MergeRequestEvent",
    "TOKEN_HEADER",
    "VerifyJobRequest",
    "WebhookAuthenticationError",
    "WebhookVerificationError",
    "delivery_key",
    "map_event_to_job_request",
    "outbox_idempotency_key",
    "parse_merge_request_event",
    "process_webhook",
    "verify_token",
]
