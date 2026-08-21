"""Unit tests - GitLab webhook + MR integration (first slice).

Fake requests only: raw bytes bodies + header dicts drive the dry
process_webhook pipeline; the job creator is a recording fake. No HTTP,
no Docker, no live API wiring.
"""

import json

import pytest

from integrations.gitlab import (
    ACTION_DUPLICATE_DELIVERY,
    ACTION_IGNORED,
    ACTION_JOB_CREATED,
    DELIVERY_HEADER,
    EVENT_HEADER,
    GITLAB_WEBHOOK_TOKEN,
    MERGE_REQUEST_HOOK,
    TOKEN_HEADER,
    DeliveryRegistry,
    EventParseError,
    GitLabMRConnector,
    VerifyJobRequest,
    WebhookAuthenticationError,
    WebhookVerificationError,
    process_webhook,
    verify_token,
)
from integrations.gitlab.events import parse_merge_request_event

TOKEN = "whsec_gitlab_test"
EVENT_UUID = "e9f2c1b3-6a11-4c22-9a00-7b8c9d0e1f2a"


def _mr_payload(action: str = "open") -> dict:
    return {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "project": {
            "id": 123,
            "path_with_namespace": "acme/backend",
            "http_url_to_repo": "https://gitlab.example.com/acme/backend.git",
        },
        "object_attributes": {
            "iid": 17,
            "action": action,
            "source_branch": "feature/specproof-gate",
            "target_branch": "main",
            "state": "opened",
        },
    }


def _headers(
    token: str = TOKEN,
    uuid: str = EVENT_UUID,
    event: str = MERGE_REQUEST_HOOK,
) -> dict[str, str]:
    return {
        TOKEN_HEADER: token,
        DELIVERY_HEADER: uuid,
        EVENT_HEADER: event,
    }


class RecordingJobCreator:
    """Fake job creator: records every request and returns sequential ids."""

    def __init__(self) -> None:
        self.requests: list[VerifyJobRequest] = []
        self.counter = 0

    def __call__(self, request: VerifyJobRequest) -> str:
        self.requests.append(request)
        self.counter += 1
        return f"job-{self.counter}"


class ExplodingJobCreator:
    """Fake job creator that always fails (retry-semantics tests)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: VerifyJobRequest) -> str:
        self.calls += 1
        raise RuntimeError("job persistence failed")


# --- X-Gitlab-Token verification -------------------------------------------


def test_verify_token_accepts_matching_token():
    assert verify_token(TOKEN, TOKEN) is True


def test_verify_token_rejects_wrong_token():
    assert verify_token("definitely-not-the-token", TOKEN) is False


def test_verify_token_rejects_missing_header():
    assert verify_token(None, TOKEN) is False


def test_verify_token_missing_secret_fails_closed(monkeypatch):
    monkeypatch.setenv(GITLAB_WEBHOOK_TOKEN, "")
    with pytest.raises(WebhookVerificationError):
        verify_token(TOKEN)


def test_verify_token_compares_timing_safe(monkeypatch):
    import integrations.gitlab.verification as verification_module

    calls = []

    def spy(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return left == right

    monkeypatch.setattr(verification_module, "compare_digest", spy)
    assert verify_token(TOKEN, TOKEN) is True
    assert calls == [(b"whsec_gitlab_test", b"whsec_gitlab_test")]


# --- event parse ------------------------------------------------------------


def test_event_parse_open_mr_extracts_branches_and_project():
    event = parse_merge_request_event(_mr_payload())
    assert event.action == "open"
    assert event.source_branch == "feature/specproof-gate"
    assert event.target_branch == "main"
    assert event.project_id == 123
    assert event.merge_request_iid == 17
    assert event.project_path == "acme/backend"
    assert event.repo_url == "https://gitlab.example.com/acme/backend.git"


def test_event_parse_update_mr_action():
    event = parse_merge_request_event(_mr_payload(action="update"))
    assert event.action == "update"


def test_event_parse_rejects_non_mr_kind():
    with pytest.raises(EventParseError):
        parse_merge_request_event({"object_kind": "push", "project": {}, "object_attributes": {}})


def test_event_parse_rejects_missing_source_branch():
    payload = _mr_payload()
    del payload["object_attributes"]["source_branch"]
    with pytest.raises(EventParseError):
        parse_merge_request_event(payload)


# --- job request mapping (dry connector) ------------------------------------


def test_process_webhook_maps_mr_event_to_verify_job_request():
    creator = RecordingJobCreator()
    result = process_webhook(
        json.dumps(_mr_payload()).encode(), _headers(), creator, token=TOKEN
    )
    assert result.action == ACTION_JOB_CREATED
    assert result.job_id == "job-1"
    assert result.idempotency_key == f"gitlab:delivery:{EVENT_UUID}"
    (request,) = creator.requests
    assert request.repo_path == "https://gitlab.example.com/acme/backend.git"
    assert request.base_ref == "main"
    assert request.head_ref == "feature/specproof-gate"
    assert request.spec_path == ""
    assert request.depth == "FAST"
    assert request.provider == "gitlab"
    assert request.project_id == 123
    assert request.merge_request_iid == 17


def test_connector_process_uses_injected_creator_and_registry():
    creator = RecordingJobCreator()
    registry = DeliveryRegistry()
    connector = GitLabMRConnector(creator, token=TOKEN, registry=registry)
    result = connector.process(_mr_payload(), TOKEN, EVENT_UUID)
    assert result.action == ACTION_JOB_CREATED
    assert result.job_id == "job-1"
    assert creator.requests[0].project_id == 123


def test_env_token_used_when_token_arg_omitted(monkeypatch):
    monkeypatch.setenv(GITLAB_WEBHOOK_TOKEN, TOKEN)
    creator = RecordingJobCreator()
    result = process_webhook(
        json.dumps(_mr_payload()).encode(), _headers(), creator
    )
    assert result.action == ACTION_JOB_CREATED


def test_bad_token_raises_and_never_calls_creator():
    creator = RecordingJobCreator()
    with pytest.raises(WebhookAuthenticationError):
        process_webhook(
            json.dumps(_mr_payload()).encode(),
            _headers(token="wrong-token"),
            creator,
            token=TOKEN,
        )
    assert creator.requests == []


def test_missing_token_header_raises():
    creator = RecordingJobCreator()
    headers = {DELIVERY_HEADER: EVENT_UUID, EVENT_HEADER: MERGE_REQUEST_HOOK}
    with pytest.raises(WebhookAuthenticationError):
        process_webhook(json.dumps(_mr_payload()).encode(), headers, creator, token=TOKEN)
    assert creator.requests == []


def test_non_actionable_mr_action_ignored():
    creator = RecordingJobCreator()
    result = process_webhook(
        json.dumps(_mr_payload(action="close")).encode(),
        _headers(),
        creator,
        token=TOKEN,
    )
    assert result.action == ACTION_IGNORED
    assert creator.requests == []


def test_non_mr_event_header_ignored():
    creator = RecordingJobCreator()
    result = process_webhook(
        json.dumps(_mr_payload()).encode(),
        _headers(event="Push Hook"),
        creator,
        token=TOKEN,
    )
    assert result.action == ACTION_IGNORED
    assert creator.requests == []


def test_invalid_json_body_raises_parse_error():
    with pytest.raises(EventParseError):
        process_webhook(b"this is not json", _headers(), RecordingJobCreator(), token=TOKEN)


# --- delivery idempotency (outbox conventions) ------------------------------


def test_replay_same_delivery_is_idempotent():
    creator = RecordingJobCreator()
    registry = DeliveryRegistry()
    body = json.dumps(_mr_payload()).encode()
    first = process_webhook(body, _headers(), creator, token=TOKEN, registry=registry)
    second = process_webhook(body, _headers(), creator, token=TOKEN, registry=registry)
    assert first.action == ACTION_JOB_CREATED
    assert second.action == ACTION_DUPLICATE_DELIVERY
    assert len(creator.requests) == 1


def test_duplicate_delivery_dedupes_by_delivery_id_not_payload():
    creator = RecordingJobCreator()
    registry = DeliveryRegistry()
    opened = json.dumps(_mr_payload(action="open")).encode()
    updated = json.dumps(_mr_payload(action="update")).encode()
    first = process_webhook(opened, _headers(), creator, token=TOKEN, registry=registry)
    replay = process_webhook(updated, _headers(), creator, token=TOKEN, registry=registry)
    assert first.action == ACTION_JOB_CREATED
    assert replay.action == ACTION_DUPLICATE_DELIVERY
    assert len(creator.requests) == 1


def test_distinct_deliveries_create_distinct_jobs():
    creator = RecordingJobCreator()
    registry = DeliveryRegistry()
    body = json.dumps(_mr_payload()).encode()
    first = process_webhook(
        body, _headers(uuid="uuid-a"), creator, token=TOKEN, registry=registry
    )
    second = process_webhook(
        body, _headers(uuid="uuid-b"), creator, token=TOKEN, registry=registry
    )
    assert first.action == ACTION_JOB_CREATED
    assert second.action == ACTION_JOB_CREATED
    assert first.job_id == "job-1"
    assert second.job_id == "job-2"
    assert creator.counter == 2


def test_failed_job_creation_leaves_delivery_retryable():
    registry = DeliveryRegistry()
    failing = ExplodingJobCreator()
    body = json.dumps(_mr_payload()).encode()
    with pytest.raises(RuntimeError):
        process_webhook(body, _headers(), failing, token=TOKEN, registry=registry)
    assert failing.calls == 1
    retry = RecordingJobCreator()
    result = process_webhook(body, _headers(), retry, token=TOKEN, registry=registry)
    assert result.action == ACTION_JOB_CREATED
    assert len(retry.requests) == 1
