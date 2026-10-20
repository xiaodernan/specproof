"""Offline certificate verification tests (Phase 2, P2-3).

The point of this module is the WORDING as much as the verdict: an
unsigned document must never be described as a signed certificate. These
tests pin both.

No database, no network: the revocation log path is redirected into tmp_path
and the signing key is generated per test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence.offline_verify import (
    LEVEL_DIGEST_ATTESTATION,
    LEVEL_SIGNATURE,
    LEVEL_UNVERIFIED,
    VERDICT_INVALID_SIGNATURE,
    VERDICT_MALFORMED,
    VERDICT_UNVERIFIED,
    VERDICT_VALID,
    canonical_digest,
    describe_attestation_level,
    verify_certificate_offline,
)
from evidence.signing import generate_key_hex, public_key_hex, sign_statement


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> str:
    """A fresh Ed25519 key for every test; the env var drives the signer."""
    seed = generate_key_hex()
    monkeypatch.setenv("SPECPROOF_SIGNING_KEY", seed)
    return seed


@pytest.fixture(autouse=True)
def _no_revocation_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the revocation log at a path that does not exist.

    The env var is the single source both the verifier and the log reader
    consult, so this keeps the tests off the developer's real log file
    without patching two namespaces.
    """
    monkeypatch.setenv(
        "SPECPROOF_REVOCATION_LOG", str(tmp_path / "revocations.jsonl")
    )


def _document(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "subject": {"repository": "/repo", "commit_sha": "abc123"},
        "requirements_digest": "sha256:req",
        "result": "VERIFIED",
        "verified_contracts": 3,
        "unverified_contracts": 0,
        "evidence_digests": ["sha256:ev1", "sha256:ev2"],
        "toolchain": {"maven": "3.9.9"},
        "issued_at": "2026-10-20T00:00:00+00:00",
        "issuer": "SpecProof",
        "version": "0.1.0",
    }
    document.update(overrides)
    return document


# ── the signed case ────────────────────────────────────────────────────────


class TestSignedCertificate:
    def test_valid_signature_is_valid_and_signed(self) -> None:
        statement = sign_statement(_document())
        report = verify_certificate_offline(statement, public_key=public_key_hex())
        assert report.verdict == VERDICT_VALID
        assert report.attestation_level == LEVEL_SIGNATURE
        assert report.signature_present is True
        assert report.signature_valid is True
        assert report.subject_repository == "/repo"
        assert report.subject_commit_sha == "abc123"

    def test_signed_certificate_reports_its_digest(self) -> None:
        statement = sign_statement(_document())
        report = verify_certificate_offline(statement, public_key=public_key_hex())
        assert report.certificate_digest == canonical_digest(_document())
        assert report.certificate_digest.startswith("sha256:")

    def test_tampered_payload_breaks_the_signature(self) -> None:
        statement = sign_statement(_document())
        statement["payload"]["verified_contracts"] = 99
        report = verify_certificate_offline(statement, public_key=public_key_hex())
        assert report.signature_valid is False
        assert report.verdict == VERDICT_INVALID_SIGNATURE
        assert report.attestation_level == LEVEL_DIGEST_ATTESTATION

    def test_wrong_public_key_is_an_invalid_signature(self) -> None:
        statement = sign_statement(_document())
        other_seed = generate_key_hex()
        monkey_key = public_key_hex
        # Sign with a DIFFERENT key than the one the verifier expects.
        import evidence.signing as signing

        original = signing.load_private_key
        try:
            signing.load_private_key = lambda: signing.Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(other_seed)
            )
            statement = signing.sign_statement(_document())
        finally:
            signing.load_private_key = original
        report = verify_certificate_offline(statement, public_key=monkey_key())
        assert report.signature_valid is False
        assert report.verdict == VERDICT_INVALID_SIGNATURE


# ── the unsigned case: the wording must not drift ──────────────────────────


class TestUnsignedCertificate:
    def test_unsigned_document_is_digest_attestation_not_signed(self) -> None:
        report = verify_certificate_offline(_document())
        assert report.attestation_level == LEVEL_DIGEST_ATTESTATION
        assert report.attestation_level != LEVEL_SIGNATURE
        assert report.verdict == VERDICT_UNVERIFIED
        assert report.signature_present is False

    def test_unsigned_document_notes_that_it_proves_only_its_bytes(self) -> None:
        report = verify_certificate_offline(_document())
        assert any("no signature" in note for note in report.notes)

    def test_attestation_wording_forbids_calling_it_signed(self) -> None:
        wording = describe_attestation_level(LEVEL_DIGEST_ATTESTATION)
        assert "NOT a signed certificate" in wording
        assert "digest attestation" in wording

    def test_signed_wording_says_signed(self) -> None:
        wording = describe_attestation_level(LEVEL_SIGNATURE)
        assert "signed certificate" in wording
        assert "valid Ed25519 signature" in wording

    def test_unverified_wording(self) -> None:
        assert "unverified" in describe_attestation_level(LEVEL_UNVERIFIED)

    def test_signature_without_a_key_is_unchecked_not_valid(self) -> None:
        """No expected key ⇒ the signature was not checked ⇒ not valid."""
        statement = sign_statement(_document())
        report = verify_certificate_offline(statement, public_key=None)
        assert report.signature_present is True
        assert report.signature_valid is False
        assert report.verdict == VERDICT_UNVERIFIED
        assert any("no expected public key" in note for note in report.notes)


# ── malformed input ────────────────────────────────────────────────────────


class TestMalformed:
    def test_empty_statement_is_malformed(self) -> None:
        report = verify_certificate_offline({})
        assert report.verdict == VERDICT_MALFORMED
        assert report.attestation_level == LEVEL_UNVERIFIED

    def test_non_object_statement_is_malformed(self) -> None:
        report = verify_certificate_offline({"payload": "not a dict"})
        assert report.verdict == VERDICT_MALFORMED

    def test_random_json_is_malformed(self) -> None:
        report = verify_certificate_offline(json.loads('{"foo": "bar"}'))
        assert report.verdict == VERDICT_MALFORMED


# ── evidence digests ───────────────────────────────────────────────────────


class TestEvidenceDigests:
    def test_known_digest_is_present_and_matches(self) -> None:
        report = verify_certificate_offline(
            _document(), known_evidence_digests=["sha256:ev1", "sha256:ev2"]
        )
        assert len(report.evidence_checks) == 2
        assert all(c.present for c in report.evidence_checks)
        assert all(c.matches for c in report.evidence_checks)
        assert report.missing_evidence == []

    def test_missing_digest_is_reported_as_missing_not_mismatched(self) -> None:
        """'I do not have it' and 'the bytes differ' are different claims."""
        report = verify_certificate_offline(
            _document(), known_evidence_digests=["sha256:ev1"]
        )
        assert report.missing_evidence == ["sha256:ev2"]
        check = next(c for c in report.evidence_checks if c.digest == "sha256:ev2")
        assert check.present is False
        assert check.matches is None

    def test_the_vocabulary_carries_no_unreachable_verdict(self) -> None:
        """A word the check cannot produce is a promise the module breaks.

        The verifier holds a FLAT set of digests, so "held but different"
        is not detectable: a digest it does not hold is missing, and
        there is no third case. An earlier design carried a
        `digest_mismatch` verdict and a `mismatched_evidence` field;
        nothing ever set them, so a certificate whose evidence bytes
        differed would have been reported as `valid`.
        """
        from evidence.offline_verify import VERDICTS

        assert "digest_mismatch" not in VERDICTS
        assert not hasattr(verify_certificate_offline(
            _document(), known_evidence_digests=["sha256:ev1"]
        ), "mismatched_evidence")

    def test_bare_hex_digest_is_accepted(self) -> None:
        report = verify_certificate_offline(
            _document(evidence_digests=["ev1", "ev2"]),
            known_evidence_digests=["sha256:ev1", "sha256:ev2"],
        )
        assert report.missing_evidence == []

    def test_certificate_without_evidence_digests_notes_it(self) -> None:
        report = verify_certificate_offline(_document(evidence_digests=[]))
        assert any("no evidence digests" in note for note in report.notes)


# ── revocation ─────────────────────────────────────────────────────────────


def test_revoked_certificate_is_revoked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A revoked certificate is never served as valid, even when signed."""
    from evidence.certificate import CertificateRevocation
    from evidence.revocation_log import append_revocation

    log = tmp_path / "revocations.jsonl"
    monkeypatch.setenv("SPECPROOF_REVOCATION_LOG", str(log))
    document = _document()
    digest = canonical_digest(document)
    append_revocation(CertificateRevocation(digest, "superseded").sign())

    statement = sign_statement(document)
    report = verify_certificate_offline(statement, public_key=public_key_hex())
    assert report.revoked is True
    assert report.verdict == "revoked"


def test_unreadable_revocation_log_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """An unreadable log means the revocation state is unknown ⇒ revoked."""
    log = tmp_path / "log-as-a-directory"
    log.mkdir()
    monkeypatch.setenv("SPECPROOF_REVOCATION_LOG", str(log))
    statement = sign_statement(_document())
    report = verify_certificate_offline(statement, public_key=public_key_hex())
    assert report.revoked is True
    assert report.verdict == "revoked"
    assert "fail-closed" in report.revocation_reason


def test_absent_revocation_log_means_nothing_was_revoked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """No log at all ⇒ nothing was revoked — not a failure."""
    monkeypatch.setenv(
        "SPECPROOF_REVOCATION_LOG", str(tmp_path / "absent.jsonl")
    )
    statement = sign_statement(_document())
    report = verify_certificate_offline(statement, public_key=public_key_hex())
    assert report.revoked is False
    assert report.verdict == VERDICT_VALID


# ── the report shape ───────────────────────────────────────────────────────


def test_report_serializes_to_json(tmp_path: Path) -> None:
    import json as _json

    statement = sign_statement(_document())
    report = verify_certificate_offline(statement, public_key=public_key_hex())
    payload = report.to_dict()
    encoded = _json.dumps(payload)  # must be serializable
    assert _json.loads(encoded)["verdict"] == VERDICT_VALID
    assert payload["attestation_level"] == LEVEL_SIGNATURE
    assert payload["evidence_checks"]
