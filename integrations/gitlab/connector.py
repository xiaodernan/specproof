"""Dry GitLab MR to verify-job connector.

Maps verified merge_request events to verify-job creation requests through
an injected job-creator callable. Nothing here touches the live API or
storage: the creator is supplied by the caller, so the pipeline is
exercisable with fakes and unit tests only (no network, no Docker).

Delivery idempotency reuses the outbox conventions:

- the in-process ledger key mirrors api/routes/webhooks._delivery_key
  (sha256 of delivery id + event);
- the envelope key follows the tests/contract/test_event_envelope.py
  convention "github:delivery:d-1" -> "gitlab:delivery:<event-uuid>".

At-least-once redelivery is expected: a delivery id is recorded only after
the job creator succeeds, so a failed first attempt can be retried.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from integrations.gitlab.events import (
    ACTIONABLE_MERGE_REQUEST_ACTIONS,
    EventParseError,
    MergeRequestEvent,
    parse_merge_request_event,
)
from integrations.gitlab.verification import verify_token

EVENT_HEADER = "X-Gitlab-Event"
TOKEN_HEADER = "X-Gitlab-Token"
DELIVERY_HEADER = "X-Gitlab-Event-UUID"
MERGE_REQUEST_HOOK = "Merge Request Hook"

ACTION_JOB_CREATED = "job_created"
ACTION_DUPLICATE_DELIVERY = "duplicate_delivery"
ACTION_IGNORED = "ignored"

PROVIDER = "gitlab"
DEFAULT_DEPTH = "FAST"


class WebhookAuthenticationError(Exception):
    """Raised when the X-Gitlab-Token header does not match."""


@dataclass(frozen=True)
class VerifyJobRequest:
    """Verify-job creation request mapped from an MR event (dry).

    repo_path/base_ref/head_ref/spec_path/depth mirror the job shape the
    API persists via the transactional outbox; project_id and
    merge_request_iid carry the GitLab coordinates. spec_path stays empty:
    the worker fills it from the repo's constitution.
    """

    repo_path: str
    base_ref: str
    head_ref: str
    spec_path: str
    depth: str
    provider: str
    project_id: int
    merge_request_iid: int


@dataclass(frozen=True)
class ConnectorResult:
    """Outcome of processing one delivery (mirrors the GitHub route shape)."""

    action: str
    job_id: str | None = None
    reason: str | None = None
    idempotency_key: str | None = None


JobCreator = Callable[[VerifyJobRequest], str]


class DeliveryRegistry:
    """In-process ledger of processed delivery keys (outbox-style)."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._seen

    def record(self, key: str) -> None:
        with self._lock:
            self._seen.add(key)


def delivery_key(event_uuid: str) -> str:
    """Dedupe key for a delivery (mirrors api/routes/webhooks._delivery_key)."""
    return hashlib.sha256((event_uuid + "|" + MERGE_REQUEST_HOOK).encode()).hexdigest()


def outbox_idempotency_key(event_uuid: str) -> str:
    """Outbox envelope idempotency key for a GitLab delivery."""
    return f"{PROVIDER}:delivery:{event_uuid}"


def map_event_to_job_request(event: MergeRequestEvent) -> VerifyJobRequest:
    """Map a parsed MR event to a verify-job creation request."""
    return VerifyJobRequest(
        repo_path=event.repo_url,
        base_ref=event.target_branch,
        head_ref=event.source_branch,
        spec_path="",
        depth=DEFAULT_DEPTH,
        provider=PROVIDER,
        project_id=event.project_id,
        merge_request_iid=event.merge_request_iid,
    )


class GitLabMRConnector:
    """Dry connector: verified MR events -> job creator callable."""

    def __init__(
        self,
        job_creator: JobCreator,
        token: str | None = None,
        registry: DeliveryRegistry | None = None,
    ) -> None:
        self._job_creator = job_creator
        self._token = token
        self._registry = registry if registry is not None else DeliveryRegistry()

    def process(
        self,
        payload: Mapping[str, Any],
        token_header: str | None,
        event_uuid: str,
    ) -> ConnectorResult:
        """Verify, parse, dedupe, and (for opened/updated MRs) create a job."""
        if not verify_token(token_header, self._token):
            raise WebhookAuthenticationError("invalid X-Gitlab-Token header")
        event = parse_merge_request_event(payload)
        if event.action not in ACTIONABLE_MERGE_REQUEST_ACTIONS:
            return ConnectorResult(
                action=ACTION_IGNORED,
                reason=(
                    f"merge request action {event.action!r} is not actionable"
                ),
            )
        key = delivery_key(event_uuid)
        if self._registry.contains(key):
            return ConnectorResult(action=ACTION_DUPLICATE_DELIVERY)
        request = map_event_to_job_request(event)
        job_id = self._job_creator(request)
        self._registry.record(key)
        return ConnectorResult(
            action=ACTION_JOB_CREATED,
            job_id=job_id,
            idempotency_key=outbox_idempotency_key(event_uuid),
        )


def process_webhook(
    body: bytes,
    headers: Mapping[str, str],
    job_creator: JobCreator,
    token: str | None = None,
    registry: DeliveryRegistry | None = None,
) -> ConnectorResult:
    """Dry webhook entry point over a raw body + headers (no HTTP).

    Raises EventParseError for bodies that are not JSON objects; raises
    WebhookAuthenticationError/WebhookVerificationError via verify_token
    for a bad or unconfigured token.
    """
    if headers.get(EVENT_HEADER) != MERGE_REQUEST_HOOK:
        return ConnectorResult(
            action=ACTION_IGNORED,
            reason=(
                f"{EVENT_HEADER} {headers.get(EVENT_HEADER)!r} "
                "is not a merge request hook"
            ),
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise EventParseError("webhook body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise EventParseError("webhook body must be a JSON object")
    event_uuid = headers.get(DELIVERY_HEADER, "") or str(uuid.uuid4())
    return GitLabMRConnector(job_creator, token=token, registry=registry).process(
        payload, headers.get(TOKEN_HEADER), event_uuid
    )
