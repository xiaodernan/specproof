"""P5 tests — GitHub webhook signature verification (fail-closed) + PR closed event (#184)."""

import pytest
from fastapi.testclient import TestClient

from api.server import app
from integrations.github import (
    WebhookVerificationError,
    sign_payload,
    verify_signature,
)

SECRET = "whsec_test_1234567890"
BODY = b'{"action": "opened", "pull_request": {}}'


@pytest.fixture(autouse=True)
def secret_env(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)


@pytest.fixture(autouse=True)
def hermetic_metrics():
    """Snapshot & restore the process-global metric registry (#184).

    The webhook endpoint runs through api/server.py middleware, which
    observes `webhook_github_handling_seconds` (and counters) on every
    request. `observe_duration`'s first-ladder-wins rule means a histogram
    created HERE would silently own the name for later tests that register
    their own ladder (test_metrics_http.py's ladder-override case). Leaving
    state behind is therefore not harmless: restore, don't just clear.
    """
    import observability.metrics as metrics
    from api.routes import webhooks

    saved_counters = dict(metrics._counters)
    saved_gauges = dict(metrics._gauges)
    saved_histograms = {
        name: (ladder, list(hist)) for name, (ladder, hist) in metrics._histograms.items()
    }
    saved_events = dict(webhooks._PROCESSED_EVENTS)
    yield
    metrics._counters.clear()
    metrics._counters.update(saved_counters)
    metrics._gauges.clear()
    metrics._gauges.update(saved_gauges)
    metrics._histograms.clear()
    metrics._histograms.update(saved_histograms)
    webhooks._PROCESSED_EVENTS.clear()
    webhooks._PROCESSED_EVENTS.update(saved_events)


def test_valid_signature_accepted():
    sig = sign_payload(BODY, SECRET)
    assert verify_signature(BODY, sig)


def test_wrong_secret_rejected():
    sig = sign_payload(BODY, "other-secret")
    assert not verify_signature(BODY, sig)


def test_tampered_payload_rejected():
    sig = sign_payload(BODY, SECRET)
    assert not verify_signature(BODY + b"x", sig)


def test_missing_header_rejected():
    assert not verify_signature(BODY, None)


def test_malformed_header_rejected():
    assert not verify_signature(BODY, "not-sha256-prefix")


def test_missing_secret_fails_closed(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
    with pytest.raises(WebhookVerificationError):
        verify_signature(BODY, sign_payload(BODY, SECRET))


# ── #184: PR closed event tests ───────────────────────────────────────


def test_github_webhook_pr_closed_merged(monkeypatch):
    """PR closed with merged=true increments pr_merged_total."""
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)

    body = b'{"action": "closed", "pull_request": {"merged": true, "number": 42}}'
    sig = sign_payload(body, SECRET)

    client = TestClient(app)
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "test-delivery-1",
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["action"] == "closed"
    assert data["merged"] is True

    import observability.metrics as metrics
    snap = metrics.snapshot()
    assert snap["counters"].get("pr_merged_total") == 1.0
    assert snap["counters"].get("pr_closed_without_merge_total") is None


def test_github_webhook_pr_closed_unmerged(monkeypatch):
    """PR closed with merged=false increments pr_closed_without_merge_total."""
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)

    body = b'{"action": "closed", "pull_request": {"merged": false, "number": 43}}'
    sig = sign_payload(body, SECRET)

    client = TestClient(app)
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "test-delivery-2",
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["action"] == "closed"
    assert data["merged"] is False

    import observability.metrics as metrics
    snap = metrics.snapshot()
    assert snap["counters"].get("pr_merged_total") is None
    assert snap["counters"].get("pr_closed_without_merge_total") == 1.0


def test_github_webhook_pr_closed_merged_twice_idempotent(monkeypatch):
    """Duplicate delivery of same closed event is deduped."""
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)

    body = b'{"action": "closed", "pull_request": {"merged": true, "number": 44}}'
    sig = sign_payload(body, SECRET)
    delivery_id = "test-delivery-dup"

    client = TestClient(app)
    resp1 = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery_id,
        },
    )
    assert resp1.status_code == 202
    assert resp1.json()["action"] == "closed"

    resp2 = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": delivery_id,
        },
    )
    assert resp2.status_code == 202
    assert resp2.json()["action"] == "duplicate_delivery"

    import observability.metrics as metrics
    snap = metrics.snapshot()
    assert snap["counters"].get("pr_merged_total") == 1.0
    assert snap["counters"].get("pr_closed_without_merge_total") is None
