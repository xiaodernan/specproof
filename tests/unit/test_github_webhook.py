"""P5 tests — GitHub webhook signature verification (fail-closed)."""

import pytest

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
