"""Unit tests for the notification connector first slice (阶段8/M10).

Fakes only: a scripted httpx.BaseTransport records every request and serves
prepared responses/exceptions, so payload shape, HMAC signing, redaction,
retry classification and the unconfigured no-op all run without any network
or Docker. Fake secrets are assembled by concatenation — this file carries
no secret-shaped literals, keeping tests/security/test_no_key_leak.py green.
"""

import hashlib
import hmac
import json
from collections import deque
from typing import Any

import httpx
import pytest

from integrations.notify import (
    CAPABILITY_BLOCKS,
    CAPABILITY_HMAC,
    CAPABILITY_TEXT,
    SIGNATURE_HEADER,
    WEBHOOK_SECRET_ENV,
    WEBHOOK_URL_ENV,
    DisabledConnector,
    Notification,
    SendStatus,
    WebhookConnector,
    WebhookKind,
    build_feishu_payload,
    build_generic_payload,
    build_slack_payload,
    build_terminal_notification,
    event_type_for_verdict,
    hmac_signature,
    normalize_verdict,
    title_for_verdict,
    webhook_connector_from_env,
)

FAKE_URL = "https://hooks.example.com/services/T000/B000/XXXX"
FAKE_SECRET = "whsec_" + "a" * 24
FAKE_LLM_KEY = "sk-" + "a" * 32  # concatenated fake: never a secret literal


def _notification(**overrides: Any) -> Notification:
    values: dict[str, Any] = {
        "event_type": "verification.blocked",
        "title": "SpecProof verification blocked",
        "text": "one finding",
        "blocks": (),
        "job_id": "job-1",
    }
    values.update(overrides)
    return Notification(**values)


class RecordingTransport(httpx.BaseTransport):
    """Fake transport: serves a script of responses/exceptions, records requests."""

    def __init__(self, script: list[httpx.Response | BaseException]) -> None:
        self._script = deque(script)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self._script.popleft() if self._script else httpx.Response(200)
        if isinstance(step, BaseException):
            raise step
        return step


def _connector(
    transport: RecordingTransport,
    *,
    kind: WebhookKind = WebhookKind.GENERIC,
    secret: str | None = None,
    max_attempts: int = 3,
    sleeps: list[float] | None = None,
) -> WebhookConnector:
    recorder = sleeps if sleeps is not None else []

    def record(seconds: float) -> None:
        recorder.append(seconds)

    return WebhookConnector(
        FAKE_URL,
        kind=kind,
        secret=secret,
        transport=transport,
        max_attempts=max_attempts,
        sleep_fn=record,
    )


# --- payload shapes ---------------------------------------------------------


def test_slack_payload_shape_with_and_without_blocks():
    block = {"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}
    notification = _notification(text="hello", blocks=(block,))
    payload = build_slack_payload(notification)
    assert payload == {"text": "hello", "blocks": [block]}
    assert build_slack_payload(_notification(text="hello")) == {"text": "hello"}


def test_feishu_payload_is_minimal_text_message():
    notification = _notification(title="Blocked", text="two findings")
    assert build_feishu_payload(notification) == {
        "msg_type": "text",
        "content": {"text": "Blocked\ntwo findings"},
    }


def test_generic_payload_carries_fields_blocks_and_job_id():
    block = {"type": "divider"}
    notification = _notification(blocks=(block,), job_id="job-9")
    payload = build_generic_payload(notification)
    assert payload["event_type"] == "verification.blocked"
    assert payload["title"] == "SpecProof verification blocked"
    assert payload["text"] == "one finding"
    assert payload["job_id"] == "job-9"
    assert payload["blocks"] == [block]
    assert "blocks" not in build_generic_payload(_notification(blocks=()))


# --- send: wire shape, redaction, signing -----------------------------------


def test_send_posts_payload_and_returns_sent():
    transport = RecordingTransport([httpx.Response(200)])
    connector = _connector(transport)
    notification = _notification(
        event_type="verification.verified", title="passed", text="all green"
    )
    assert connector.send(notification) is SendStatus.SENT
    (request,) = transport.requests
    assert request.method == "POST"
    assert str(request.url) == FAKE_URL
    assert request.headers["Content-Type"] == "application/json"
    assert SIGNATURE_HEADER not in request.headers
    assert json.loads(request.content.decode("utf-8")) == {
        "event_type": "verification.verified",
        "title": "passed",
        "text": "all green",
        "job_id": "job-1",
    }
    assert connector.attempts == 1


def test_send_redacts_secret_shaped_spans():
    transport = RecordingTransport([httpx.Response(200)])
    connector = _connector(transport)
    notification = _notification(text="key leaked: " + FAKE_LLM_KEY)
    assert connector.send(notification) is SendStatus.SENT
    body = transport.requests[0].content.decode("utf-8")
    assert FAKE_LLM_KEY not in body
    assert "[REDACTED:llm_api_key]" in body


def test_send_redacts_secret_key_names():
    transport = RecordingTransport([httpx.Response(200)])
    connector = _connector(transport)
    notification = _notification(
        text="x",
        blocks=({"type": "section", "text": {"api_key": "super-secret-value"}},),
    )
    assert connector.send(notification) is SendStatus.SENT
    body = transport.requests[0].content.decode("utf-8")
    assert "super-secret-value" not in body
    assert '"api_key": "[REDACTED]"' in body


def test_generic_signs_with_hmac_over_the_redacted_body():
    transport = RecordingTransport([httpx.Response(200)])
    connector = _connector(transport, secret=FAKE_SECRET)
    notification = _notification(text="leak " + FAKE_LLM_KEY)
    assert connector.send(notification) is SendStatus.SENT
    (request,) = transport.requests
    body = request.content
    expected = "sha256=" + hmac.new(
        FAKE_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    assert request.headers[SIGNATURE_HEADER] == expected
    assert FAKE_LLM_KEY not in body.decode("utf-8")


def test_hmac_signature_is_sha256_hex():
    assert hmac_signature(b"payload", "secret") == (
        "sha256=" + hmac.new(b"secret", b"payload", hashlib.sha256).hexdigest()
    )


def test_generic_without_secret_does_not_sign():
    transport = RecordingTransport([httpx.Response(200)])
    connector = _connector(transport)
    connector.send(_notification())
    assert SIGNATURE_HEADER not in transport.requests[0].headers


def test_slack_and_feishu_never_sign_even_with_secret():
    for kind in (WebhookKind.SLACK, WebhookKind.FEISHU):
        transport = RecordingTransport([httpx.Response(200)])
        connector = _connector(transport, kind=kind, secret=FAKE_SECRET)
        assert connector.send(_notification()) is SendStatus.SENT
        assert SIGNATURE_HEADER not in transport.requests[0].headers


# --- capabilities -----------------------------------------------------------


def test_capabilities_by_kind_and_secret():
    slack = WebhookConnector(FAKE_URL, kind=WebhookKind.SLACK)
    assert slack.capabilities == frozenset({CAPABILITY_TEXT, CAPABILITY_BLOCKS})
    slack.close()
    feishu = WebhookConnector(FAKE_URL, kind=WebhookKind.FEISHU)
    assert feishu.capabilities == frozenset({CAPABILITY_TEXT})
    feishu.close()
    generic = WebhookConnector(FAKE_URL, kind=WebhookKind.GENERIC)
    assert generic.capabilities == frozenset({CAPABILITY_TEXT})
    generic.close()
    signed = WebhookConnector(FAKE_URL, kind=WebhookKind.GENERIC, secret=FAKE_SECRET)
    assert signed.capabilities == frozenset({CAPABILITY_TEXT, CAPABILITY_HMAC})
    signed.close()


def test_empty_url_raises_value_error():
    with pytest.raises(ValueError):
        WebhookConnector("   ")


# --- retry classification (providers.resilience.classify_retry) -------------


def test_retries_503_then_succeeds_with_backoff_sleep():
    sleeps: list[float] = []
    transport = RecordingTransport([httpx.Response(503), httpx.Response(200)])
    connector = _connector(transport, sleeps=sleeps)
    assert connector.send(_notification()) is SendStatus.SENT
    assert len(transport.requests) == 2
    assert sleeps == [1.0]
    assert connector.attempts == 2


def test_no_retry_on_400():
    transport = RecordingTransport([httpx.Response(400)])
    connector = _connector(transport)
    assert connector.send(_notification()) is SendStatus.FAILED
    assert len(transport.requests) == 1
    assert connector.last_failure_reason == "http_400_no_retry"


def test_retry_exhausted_on_503_returns_failed():
    transport = RecordingTransport(
        [httpx.Response(503), httpx.Response(503), httpx.Response(503)]
    )
    connector = _connector(transport)
    assert connector.send(_notification()) is SendStatus.FAILED
    assert len(transport.requests) == 3
    assert connector.last_failure_reason == "http_503_retry"


def test_timeout_is_retryable_until_attempts_exhausted():
    sleeps: list[float] = []
    transport = RecordingTransport(
        [httpx.TimeoutException("connect timed out")] * 3
    )
    connector = _connector(transport, sleeps=sleeps)
    assert connector.send(_notification()) is SendStatus.FAILED
    assert len(transport.requests) == 3
    assert connector.last_failure_reason == "timeout"
    assert sleeps == [1.0, 2.0]


def test_connection_error_is_retryable():
    sleeps: list[float] = []
    transport = RecordingTransport([httpx.ConnectError("boom")] * 3)
    connector = _connector(transport, sleeps=sleeps)
    assert connector.send(_notification()) is SendStatus.FAILED
    assert len(transport.requests) == 3
    assert connector.last_failure_reason == "connection"
    assert sleeps == [1.0, 2.0]


# --- unconfigured -> disabled no-op ------------------------------------------


def test_unconfigured_from_env_is_disabled_noop(monkeypatch):
    monkeypatch.delenv(WEBHOOK_URL_ENV, raising=False)
    monkeypatch.delenv(WEBHOOK_SECRET_ENV, raising=False)
    connector = webhook_connector_from_env()
    assert isinstance(connector, DisabledConnector)
    assert connector.name == "disabled"
    assert connector.capabilities == frozenset()
    assert connector.send(_notification()) is SendStatus.DISABLED


def test_factory_reads_env_only(monkeypatch):
    monkeypatch.setenv(WEBHOOK_URL_ENV, FAKE_URL)
    monkeypatch.setenv(WEBHOOK_SECRET_ENV, FAKE_SECRET)
    connector = webhook_connector_from_env(kind=WebhookKind.SLACK)
    assert isinstance(connector, WebhookConnector)
    assert connector.url == FAKE_URL
    assert connector.secret == FAKE_SECRET
    assert connector.kind is WebhookKind.SLACK
    assert connector.capabilities == frozenset({CAPABILITY_TEXT, CAPABILITY_BLOCKS})
    connector.close()


# --- terminal-event templates ------------------------------------------------


BLOCKED_SUMMARY: dict[str, Any] = {
    "verdict": "BLOCKED",
    "contracts_total": 4,
    "matrix_passed": 3,
    "matrix_failed": 1,
    "matrix_unverified": 0,
    "findings": [
        {
            "id": "f-1",
            "severity": "BLOCKER",
            "contract_id": "AUTH-01",
            "confidence": 0.95,
            "evidence_type": "runtime",
            "type": "auth",
            "location": "SecurityConfig.java:12",
            "description": "auth bypass on changeEmail",
        }
    ],
    "capsules": ["capsule-AUTH-01.zip"],
    "report_path": "reports/report.html",
    "retrieval_note": "",
    "errors": [],
}


def test_blocked_template_maps_summary_fields():
    notification = build_terminal_notification("job-7", BLOCKED_SUMMARY)
    assert notification.event_type == "verification.blocked"
    assert (
        notification.title
        == "SpecProof verification blocked — human review required"
    )
    assert notification.job_id == "job-7"
    assert "Verdict: BLOCKED" in notification.text
    assert "Contracts: 4 total — 3 passed, 1 failed, 0 unverified." in notification.text
    assert "[BLOCKER] AUTH-01: auth bypass on changeEmail" in notification.text
    assert "Capsules: 1" in notification.text
    assert "Report: reports/report.html" in notification.text
    assert notification.blocks[0]["type"] == "header"
    slack_payload = build_slack_payload(notification)
    assert slack_payload["text"] == notification.text
    assert slack_payload["blocks"] == list(notification.blocks)


def test_verified_and_failed_templates():
    verified = build_terminal_notification(
        "job-8",
        {
            "verdict": "verified",
            "contracts_total": 3,
            "matrix_passed": 3,
            "matrix_failed": 0,
            "matrix_unverified": 0,
            "findings": [],
            "capsules": [],
            "report_path": "",
            "errors": [],
        },
    )
    assert verified.event_type == "verification.verified"
    assert verified.title == "SpecProof verification passed"

    failed = build_terminal_notification(
        "job-9",
        {
            "verdict": "FAILED",
            "contracts_total": 1,
            "matrix_passed": 0,
            "matrix_failed": 0,
            "matrix_unverified": 1,
            "findings": [],
            "capsules": [],
            "report_path": "",
            "errors": ["maven exploded"],
        },
    )
    assert failed.event_type == "verification.failed"
    assert "Errors: 1" in failed.text


def test_needs_review_spellings_normalize():
    assert normalize_verdict("VERIFIED") == "VERIFIED"
    assert normalize_verdict(" blocked ") == "BLOCKED"
    assert normalize_verdict("NEEDS REVIEW") == "NEEDS_REVIEW"
    assert (
        normalize_verdict("NEEDS REVIEW (verification incomplete)")
        == "NEEDS_REVIEW"
    )
    summary: dict[str, Any] = {
        **BLOCKED_SUMMARY,
        "verdict": "NEEDS REVIEW (verification incomplete)",
        "findings": [],
        "capsules": [],
        "report_path": "",
        "matrix_failed": 0,
    }
    notification = build_terminal_notification("job-10", summary)
    assert notification.event_type == "verification.needs_review"
    assert notification.title == "SpecProof verification needs review"


def test_unknown_verdict_raises():
    with pytest.raises(ValueError):
        build_terminal_notification("job-x", {"verdict": "RUNNING"})
    with pytest.raises(ValueError):
        event_type_for_verdict("RUNNING")
    with pytest.raises(ValueError):
        title_for_verdict("RUNNING")


def test_feishu_template_payload_is_minimal():
    notification = build_terminal_notification("job-11", BLOCKED_SUMMARY)
    payload = build_feishu_payload(notification)
    assert payload == {
        "msg_type": "text",
        "content": {"text": notification.title + "\n" + notification.text},
    }
