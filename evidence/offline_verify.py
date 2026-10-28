"""Offline certificate verification and digest-mismatch reporting (P2-3).

A certificate that was issued months ago must still be checkable by an
auditor who has only the file and a public key — no database, no network,
no trust service. This module is that check, and it is deliberately
EXPLICIT about what it found rather than collapsing everything into a
boolean.

Attestation levels (§6.9 of the roadmap, "KMS/HSM 未完成前只能称为
digest attestation，不可称为正式签名证书"):

``signature``
    The statement carries a valid Ed25519 signature over the canonical
    payload, made by the expected key.

``digest_attestation``
    The statement is well-formed and its canonical digest is computable,
    but there is NO valid signature. The document proves WHAT it says
    (its own bytes) and nothing about WHO said it. Calling this "signed"
    would be the exact lie the roadmap forbids.

``unverified``
    The statement could not be parsed as a certificate at all.

Every check is reported separately so a reader can see WHICH part failed:
a revoked certificate with a valid signature is a different situation from
a certificate whose evidence digests do not match, and both are different
from one that was never signed.

There is deliberately NO ``digest_mismatch`` verdict. The verifier is
handed a flat set of digests it holds; a digest the certificate names but
the verifier does not hold is reported as MISSING, and "I do not have it"
and "the bytes differ" are different claims — and with a flat set of held
digests the second one is not even detectable. An earlier design of this
module carried a ``digest_mismatch`` word and a ``mismatched_evidence``
field; both were unreachable (nothing ever set them), and a vocabulary that
promises a verdict the check cannot produce is the same kind of lie this
module exists to avoid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from contracts.clock import utc_now_iso
from evidence.revocation_log import default_log_path, is_revoked
from evidence.signing import verify_statement

#: Attestation levels — the vocabulary a reader must use to describe what
#: a certificate actually proves.
LEVEL_SIGNATURE = "signature"
LEVEL_DIGEST_ATTESTATION = "digest_attestation"
LEVEL_UNVERIFIED = "unverified"

ATTESTATION_LEVELS: tuple[str, ...] = (
    LEVEL_SIGNATURE,
    LEVEL_DIGEST_ATTESTATION,
    LEVEL_UNVERIFIED,
)

#: Overall verification verdicts.
#:
#: No ``digest_mismatch`` — see the module docstring: the verifier holds a
#: flat set of digests, so "held but different" is not detectable, and a
#: digest it does not hold is reported as MISSING.
VERDICT_VALID = "valid"
VERDICT_INVALID_SIGNATURE = "invalid_signature"
VERDICT_REVOKED = "revoked"
VERDICT_MALFORMED = "malformed"
VERDICT_UNVERIFIED = "unverified"

VERDICTS: tuple[str, ...] = (
    VERDICT_VALID,
    VERDICT_INVALID_SIGNATURE,
    VERDICT_REVOKED,
    VERDICT_MALFORMED,
    VERDICT_UNVERIFIED,
)

#: The in-toto statement type this module understands.
STATEMENT_TYPE = "https://specproof.dev/attestation/v0.1"


def canonical_digest(payload: dict[str, Any]) -> str:
    """Canonical SHA-256 digest of a document (sorted keys, no whitespace)."""
    import hashlib

    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _normalize_digest(value: str) -> str:
    """Accept "sha256:<hex>" and bare "<hex>" as the same digest."""
    text = value.strip()
    if text.startswith("sha256:"):
        text = text[len("sha256:"):]
    return text.lower()


@dataclass
class EvidenceDigestCheck:
    """One evidence digest named in the certificate, checked against the
    digests the verifier actually holds."""

    digest: str
    present: bool
    matches: bool | None = None  # None = nothing to compare against

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "present": self.present,
            "matches": self.matches,
        }


@dataclass
class VerificationReport:
    """The full offline verification result — every check, nothing hidden."""

    verdict: str
    attestation_level: str
    certificate_digest: str = ""
    signature_present: bool = False
    signature_valid: bool = False
    signature_keyid: str = ""
    revoked: bool = False
    revocation_reason: str = ""
    evidence_checks: list[EvidenceDigestCheck] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    subject_repository: str = ""
    subject_commit_sha: str = ""
    issued_at: str = ""
    verified_at: str = field(default_factory=utc_now_iso)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "attestation_level": self.attestation_level,
            "certificate_digest": self.certificate_digest,
            "signature_present": self.signature_present,
            "signature_valid": self.signature_valid,
            "signature_keyid": self.signature_keyid,
            "revoked": self.revoked,
            "revocation_reason": self.revocation_reason,
            "evidence_checks": [c.to_dict() for c in self.evidence_checks],
            "missing_evidence": list(self.missing_evidence),
            "subject_repository": self.subject_repository,
            "subject_commit_sha": self.subject_commit_sha,
            "issued_at": self.issued_at,
            "verified_at": self.verified_at,
            "notes": list(self.notes),
        }


def _extract_payload(statement: dict[str, Any]) -> dict[str, Any] | None:
    """The certificate document inside a signed statement (or the document
    itself when it was stored unsigned)."""
    payload = statement.get("payload")
    if isinstance(payload, dict):
        return payload
    # An unsigned certificate stored directly: it has the document's own
    # fields (subject/result/issuer), not an envelope.
    if isinstance(statement.get("subject"), dict) and "result" in statement:
        return statement
    return None


def _read_revocation(certificate_digest: str) -> tuple[bool, str]:
    """(revoked, reason) from the revocation log.

    An unreadable log is treated as REVOKED (fail-closed): a certificate
    whose revocation state cannot be established must not be served as
    valid.
    """
    if not certificate_digest:
        return False, ""
    try:
        if not default_log_path().exists():
            return False, ""
        if is_revoked(certificate_digest):
            return True, "revoked (reason not recorded in the log entry)"
        return False, ""
    except Exception:  # noqa: BLE001 — unreadable log ⇒ fail closed
        return True, "revocation log unreadable — treated as revoked (fail-closed)"


def verify_certificate_offline(
    statement: dict[str, Any],
    *,
    public_key: str | None = None,
    known_evidence_digests: list[str] | None = None,
) -> VerificationReport:
    """Verify a certificate document without touching the database or network.

    ``statement`` is either a signed in-toto statement
    (``{"payload": ..., "signatures": [...]}``) or an unsigned certificate
    document. ``public_key`` is the expected Ed25519 public key (hex); when
    it is absent the signature cannot be checked and the attestation level
    is ``digest_attestation`` — never "signature".

    ``known_evidence_digests`` are the digests the verifier actually holds.
    A digest the certificate names but the verifier does not hold is
    reported as MISSING, not as a mismatch: "I do not have it" and "the
    bytes differ" are different claims.
    """
    report = VerificationReport(verdict=VERDICT_UNVERIFIED, attestation_level=LEVEL_UNVERIFIED)

    if not isinstance(statement, dict) or not statement:
        report.verdict = VERDICT_MALFORMED
        report.notes.append("the statement is not a JSON object")
        return report

    payload = _extract_payload(statement)
    if payload is None:
        report.verdict = VERDICT_MALFORMED
        report.notes.append(
            "the statement carries neither an in-toto payload nor a "
            "certificate document"
        )
        return report

    report.certificate_digest = canonical_digest(payload)
    subject = payload.get("subject")
    if isinstance(subject, dict):
        report.subject_repository = str(subject.get("repository") or "")
        report.subject_commit_sha = str(subject.get("commit_sha") or "")
    report.issued_at = str(payload.get("issued_at") or "")

    # ── signature ─────────────────────────────────────────────────
    signatures = statement.get("signatures")
    has_signatures = isinstance(signatures, list) and bool(signatures)
    report.signature_present = has_signatures
    if has_signatures and isinstance(signatures, list):
        first = signatures[0]
        if isinstance(first, dict):
            report.signature_keyid = str(first.get("keyid") or "")

    if has_signatures and public_key:
        report.signature_valid = verify_statement(statement, public_key)
    elif has_signatures and not public_key:
        report.notes.append(
            "the statement carries a signature but no expected public key was "
            "supplied — the signature was NOT checked"
        )
    else:
        report.notes.append(
            "the statement carries no signature — it proves its own bytes only"
        )

    # ── attestation level ──────────────────────────────────────────
    if report.signature_valid:
        report.attestation_level = LEVEL_SIGNATURE
    else:
        report.attestation_level = LEVEL_DIGEST_ATTESTATION
        if has_signatures and public_key:
            report.notes.append(
                "the signature did not verify against the supplied public key"
            )

    # ── evidence digests ───────────────────────────────────────────
    known = {
        _normalize_digest(d) for d in (known_evidence_digests or []) if d
    }
    named = payload.get("evidence_digests")
    if isinstance(named, list):
        for raw in named:
            digest = str(raw)
            check = EvidenceDigestCheck(
                digest=digest,
                present=_normalize_digest(digest) in known,
            )
            if check.present:
                check.matches = True
            else:
                report.missing_evidence.append(digest)
            report.evidence_checks.append(check)
        if not named:
            report.notes.append(
                "the certificate names no evidence digests — nothing to compare"
            )
    else:
        report.notes.append(
            "the certificate names no evidence digests — nothing to compare"
        )

    # ── revocation ─────────────────────────────────────────────────
    revoked, reason = _read_revocation(report.certificate_digest)
    report.revoked = revoked
    report.revocation_reason = reason

    # ── verdict ────────────────────────────────────────────────────
    if revoked:
        report.verdict = VERDICT_REVOKED
    elif report.signature_present and public_key and not report.signature_valid:
        # The signature was CHECKED and did not verify. An unchecked
        # signature must never land here: "I could not check it" and "it is
        # wrong" are different claims, and reporting the second when only
        # the first is known would be a lie about the artifact.
        report.verdict = VERDICT_INVALID_SIGNATURE
    elif not report.signature_present or not public_key:
        # Either there is no signature at all, or there is one but no
        # expected key to check it against. Both leave the document
        # UNVERIFIED as an attestation — never "valid".
        report.verdict = VERDICT_UNVERIFIED
    else:
        report.verdict = VERDICT_VALID

    if report.missing_evidence:
        report.notes.append(
            f"{len(report.missing_evidence)} evidence digest(s) named by the "
            "certificate are not held by the verifier"
        )
    return report


def describe_attestation_level(level: str) -> str:
    """The wording a reader must use for an attestation level.

    The roadmap forbids calling an unsigned document a "signed
    certificate"; the wording is defined HERE so the CLI, the API, the MCP
    tool and the report cannot drift into calling it that.
    """
    if level == LEVEL_SIGNATURE:
        return (
            "signed certificate — the statement carries a valid Ed25519 "
            "signature over its canonical payload"
        )
    if level == LEVEL_DIGEST_ATTESTATION:
        return (
            "digest attestation (NOT a signed certificate) — the document "
            "proves its own bytes and its own digest, but nothing about who "
            "issued it"
        )
    return "unverified — the statement could not be read as a certificate"


__all__ = [
    "ATTESTATION_LEVELS",
    "LEVEL_DIGEST_ATTESTATION",
    "LEVEL_SIGNATURE",
    "LEVEL_UNVERIFIED",
    "STATEMENT_TYPE",
    "VERDICTS",
    "VERDICT_INVALID_SIGNATURE",
    "VERDICT_MALFORMED",
    "VERDICT_REVOKED",
    "VERDICT_UNVERIFIED",
    "VERDICT_VALID",
    "EvidenceDigestCheck",
    "VerificationReport",
    "canonical_digest",
    "describe_attestation_level",
    "verify_certificate_offline",
]
