"""Webhook replay-protection security tests (工业化指南 §14 任务 11 残留).

Required matrix:
- duplicate delivery id            -> idempotent single effect
- old valid signature replayed     -> no duplicate job
- invalid signature                -> rejected (401)
- timestamp outside tolerance      -> rejected (401)
- missing header                   -> rejected (signature 401 / delivery 400)

Plus the honest edges around the replay window:
- unparseable/non-finite signed timestamps fail closed
- a fresh signed timestamp is accepted (the optional header never
  over-blocks senders that do attach it)
- a stale signed timestamp is rejected even for a never-seen delivery
  (the window is the durable backstop when in-memory dedupe cannot help)
- documented limitation pin: GitHub-native deliveries sign only the body,
  so a captured delivery replayed under a NEW X-GitHub-Delivery value
  still verifies and enqueues again (see test below).

Runs WITHOUT Docker or live infrastructure: MySQLStore is faked and the
"single effect" is asserted on the transactional outbox write count.
"""

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.webhooks as webhooks_module
from api.server import app
from integrations.github import sign_payload, sign_payload_with_timestamp

SECRET = "whsec_replay_test"


class FakeMySQL:
    """Counts the outbox-side effect; never touches a real database."""

    jobs: list[dict[str, Any]] = []
    outbox_writes: int = 0

    def create_job_with_outbox(self, job: dict[str, Any]) -> str:
        FakeMySQL.jobs.append(job)
        FakeMySQL.outbox_writes += 1
        return str(job["id"])

    def set_job_github_check(
        self, job_id: str, check_meta: dict[str, Any]
    ) -> None:
        """Check runs are irrelevant to replay protection; nothing to record."""


@pytest.fixture(autouse=True)
def webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)


@pytest.fixture()
def fake_mysql(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    FakeMySQL.jobs = []
    FakeMySQL.outbox_writes = 0
    webhooks_module._PROCESSED_EVENTS.clear()
    monkeypatch.setattr(webhooks_module, "MySQLStore", FakeMySQL)
    yield
    webhooks_module._PROCESSED_EVENTS.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _pr_event_body() -> dict[str, Any]:
    return {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "base": {"ref": "main", "sha": "base-sha"},
            "head": {"ref": "feature/x", "sha": "head-sha"},
        },
        "repository": {"clone_url": "https://github.com/acme/repo.git"},
    }


def _headers(
    *,
    delivery: str | None,
    timestamp: str | None,
    signature: str | None,
) -> dict[str, str]:
    """Assemble webhook headers; a None value omits the header entirely."""
    headers: dict[str, str] = {"X-GitHub-Event": "pull_request"}
    if delivery is not None:
        headers["X-GitHub-Delivery"] = delivery
    if timestamp is not None:
        headers["X-Signature-Timestamp"] = timestamp
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return headers


def _post(
    client: TestClient, raw: bytes, headers: dict[str, str]
) -> tuple[int, Any]:
    resp = client.post("/webhooks/github", content=raw, headers=headers)
    return resp.status_code, resp.json()


def test_duplicate_delivery_id_single_effect(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery="d-replay-1", timestamp=None, signature=sign_payload(raw, SECRET)
    )
    first_status, first_body = _post(client, raw, headers)
    second_status, second_body = _post(client, raw, headers)
    assert first_status == 202
    assert first_body["action"] == "job_created"
    assert second_status == 202
    assert second_body["action"] == "duplicate_delivery"
    assert len(FakeMySQL.jobs) == 1
    assert FakeMySQL.outbox_writes == 1


def test_replayed_old_valid_signature_no_duplicate(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery="d-replay-2", timestamp=None, signature=sign_payload(raw, SECRET)
    )
    first_status, first_body = _post(client, raw, headers)
    assert first_status == 202
    assert first_body["action"] == "job_created"
    # The exact original wire bytes replay: same body, same HMAC, same
    # delivery id — GitHub at-least-once redelivery, not a forgery.
    replay_status, replay_body = _post(client, raw, headers)
    assert replay_status == 202
    assert replay_body["action"] == "duplicate_delivery"
    assert len(FakeMySQL.jobs) == 1
    assert FakeMySQL.outbox_writes == 1


def test_invalid_signature_rejected(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery="d-replay-3", timestamp=None, signature="sha256=" + "0" * 64
    )
    status, body = _post(client, raw, headers)
    assert status == 401
    assert body["error"]["code"] == "AUTH_REQUIRED"
    assert FakeMySQL.jobs == []
    assert FakeMySQL.outbox_writes == 0


def test_timestamp_outside_tolerance_rejected(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    stale = str(int(time.time()) - 3600)
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery="d-replay-4",
        timestamp=stale,
        signature=sign_payload_with_timestamp(raw, stale, SECRET),
    )
    status, body = _post(client, raw, headers)
    assert status == 401
    assert body["detail"] == "Webhook timestamp outside tolerance"
    assert body["error"]["code"] == "AUTH_REQUIRED"
    assert FakeMySQL.jobs == []
    assert FakeMySQL.outbox_writes == 0


def test_missing_signature_header_rejected(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(delivery="d-replay-5", timestamp=None, signature=None)
    status, body = _post(client, raw, headers)
    assert status == 401
    assert body["detail"] == "Invalid webhook signature"
    assert FakeMySQL.jobs == []


def test_missing_delivery_header_rejected(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery=None, timestamp=None, signature=sign_payload(raw, SECRET)
    )
    status, body = _post(client, raw, headers)
    assert status == 400
    assert body["detail"] == "Missing X-GitHub-Delivery header"
    assert FakeMySQL.jobs == []
    assert FakeMySQL.outbox_writes == 0


@pytest.mark.parametrize("bad_timestamp", ["not-a-number", "nan", "inf", "-inf"])
def test_unparseable_timestamp_rejected(
    fake_mysql: Iterator[None], client: TestClient, bad_timestamp: str
) -> None:
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery="d-replay-7",
        timestamp=bad_timestamp,
        signature=sign_payload_with_timestamp(raw, bad_timestamp, SECRET),
    )
    status, body = _post(client, raw, headers)
    assert status == 401
    assert body["detail"] == "Invalid webhook timestamp"
    assert FakeMySQL.jobs == []


def test_fresh_signed_timestamp_accepted(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    fresh = str(int(time.time()))
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery="d-replay-8",
        timestamp=fresh,
        signature=sign_payload_with_timestamp(raw, fresh, SECRET),
    )
    status, body = _post(client, raw, headers)
    assert status == 202
    assert body["action"] == "job_created"
    assert len(FakeMySQL.jobs) == 1
    assert FakeMySQL.outbox_writes == 1


def test_stale_signed_timestamp_rejected_even_for_unknown_delivery(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    """The replay window must not depend on the in-memory dedupe set."""
    stale = str(int(time.time()) - 3600)
    raw = json.dumps(_pr_event_body()).encode()
    headers = _headers(
        delivery="d-replay-9",
        timestamp=stale,
        signature=sign_payload_with_timestamp(raw, stale, SECRET),
    )
    status, body = _post(client, raw, headers)
    assert status == 401
    assert body["detail"] == "Webhook timestamp outside tolerance"
    assert FakeMySQL.jobs == []


def test_unsigned_replay_with_new_delivery_documented_limitation(
    fake_mysql: Iterator[None], client: TestClient
) -> None:
    """Pin the honest residual risk of the GitHub wire format.

    GitHub signs only the body, and the delivery id lives in an unsigned
    header. A captured valid delivery can therefore be replayed under a
    NEW X-GitHub-Delivery value: the HMAC still verifies and the dedupe
    set never saw that id, so a second job is enqueued. This test pins
    that current behavior instead of pretending it is closed. Senders
    that sign timestamps are covered by the replay window (see
    test_stale_signed_timestamp_rejected_even_for_unknown_delivery).
    """
    raw = json.dumps(_pr_event_body()).encode()
    signature = sign_payload(raw, SECRET)
    first_headers = _headers(
        delivery="d-replay-10", timestamp=None, signature=signature
    )
    first_status, first_body = _post(client, raw, first_headers)
    assert first_status == 202
    assert first_body["action"] == "job_created"
    replay_headers = _headers(
        delivery="d-replay-10-again", timestamp=None, signature=signature
    )
    replay_status, replay_body = _post(client, raw, replay_headers)
    assert replay_status == 202
    assert replay_body["action"] == "job_created"
    assert len(FakeMySQL.jobs) == 2
