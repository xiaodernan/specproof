"""P5 unit tests — Ed25519 signed attestations."""


import pytest

from evidence.signing import (
    SigningError,
    generate_key_hex,
    public_key_hex,
    sign_json_document,
    verify_statement,
)

KEY = generate_key_hex()


@pytest.fixture(autouse=True)
def signing_env(monkeypatch):
    monkeypatch.setenv("SPECPROOF_SIGNING_KEY", KEY)


def test_sign_and_verify_roundtrip():
    payload = {"subject": {"commit_sha": "abc"}, "result": "VERIFIED"}
    statement = sign_json_document(payload)
    assert statement["_type"].startswith("https://specproof.dev/")
    assert len(statement["signatures"]) == 1
    assert statement["payload"] == payload
    assert verify_statement(statement, public_key_hex())


def test_tampered_payload_rejected():
    statement = sign_json_document({"result": "VERIFIED", "contracts": 3})
    statement["payload"]["result"] = "REJECTED"
    assert not verify_statement(statement, public_key_hex())


def test_wrong_key_rejected(monkeypatch):
    statement = sign_json_document({"result": "VERIFIED"})
    other = generate_key_hex()
    monkeypatch.setenv("SPECPROOF_SIGNING_KEY", other)
    assert not verify_statement(statement, public_key_hex())


def test_missing_key_raises(monkeypatch):
    monkeypatch.setenv("SPECPROOF_SIGNING_KEY", "")
    monkeypatch.setenv("SPECPROOF_SIGNING_KEY_FILE", "")
    with pytest.raises(SigningError):
        sign_json_document({"result": "VERIFIED"})


def test_invalid_key_length_raises(monkeypatch):
    monkeypatch.setenv("SPECPROOF_SIGNING_KEY", "abcd")
    with pytest.raises(SigningError):
        sign_json_document({"result": "VERIFIED"})
