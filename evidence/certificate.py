"""Merge Certificate — cryptographic attestation of verification results.

Honesty contract (v2):
- A certificate is issued ONLY when every contract is PASS with evidence
  (unverified == 0 and failed == 0).
- Otherwise the pipeline writes a Rejection Notice instead — the absence of
  a certificate is meaningful and is never papered over.
- The unsigned statement carries SHA-256 digests over the recorded
  evidence; Ed25519 signing of the canonical statement is layered on top
  by evidence/signing.py (P5 core, in-toto style) when a signing key is
  configured. SHA-256 alone is never called a signature.

Revocation (v2, #134):
- A certificate can be revoked by its issuer. The revocation is a signed
  document that references the original certificate by its canonical
  SHA-256 digest and states the revocation reason.
- Revocations are immutable once signed and are stored in a append-only
  revocation log (JSONL file, one revocation per line).
- Verification MUST check the revocation log before trusting a certificate.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from evidence.verdict import evaluate_verification, evidence_references


class MergeCertificate:
    """Attestation of a fully verified PR (in-toto Statement style)."""

    def __init__(
        self,
        repository: str,
        commit_sha: str,
        requirements_digest: str,
        verified_contracts: int,
        evidence_digests: list[str],
        toolchain: dict[str, str],
        extension: dict[str, Any] | None = None,
    ) -> None:
        # §18.1: the optional extension carries {"lineage_root",
        # "lineage_nodes", "lineage_edges"}. Old certificates without it stay
        # verifiable — the key is simply absent from to_dict() when unset.
        self.subject = {
            "repository": repository,
            "commit_sha": commit_sha,
        }
        self.requirements_digest = requirements_digest
        self.verified_contracts = verified_contracts
        self.evidence_digests = evidence_digests
        self.toolchain = toolchain
        self.extension = dict(extension or {})
        self.issued_at = datetime.now(UTC).isoformat()
        self.issuer = "SpecProof"
        self.version = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        document = {
            "subject": self.subject,
            "requirements_digest": self.requirements_digest,
            "result": "VERIFIED",
            "verified_contracts": self.verified_contracts,
            "unverified_contracts": 0,
            "evidence_digests": self.evidence_digests,
            "toolchain": self.toolchain,
            "issued_at": self.issued_at,
            "issuer": self.issuer,
            "version": self.version,
        }
        if self.extension:
            document["extension"] = dict(self.extension)
        return document

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def canonical_digest(self) -> str:
        """The canonical SHA-256 digest of this certificate's payload.

        This is the stable identifier used by revocations to reference
        the exact certificate they revoke. It is the SHA-256 of the
        canonical JSON (sorted keys, no whitespace) of the certificate's
        to_dict() output, prefixed with "sha256:".
        """
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(canonical).hexdigest()


class CertificateRevocation:
    """A signed revocation of a previously issued MergeCertificate.

    The revocation is a signed statement that identifies the target
    certificate by its canonical SHA-256 digest and provides the
    revocation reason. It is signed with the same Ed25519 key used for
    certificate signing, so verification is identical.
    """

    def __init__(
        self,
        target_certificate_digest: str,
        reason: str,
        revoked_by: str = "SpecProof",
    ) -> None:
        if not target_certificate_digest.startswith("sha256:"):
            raise ValueError(
                "target_certificate_digest must be a sha256: digest"
            )
        if not reason or len(reason.strip()) < 3:
            raise ValueError("revocation reason must be at least 3 characters")
        self.target_certificate_digest = target_certificate_digest
        self.reason = reason.strip()
        self.revoked_by = revoked_by
        self.revoked_at = datetime.now(UTC).isoformat()
        self.version = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "_type": "https://specproof.dev/revocation/v0.1",
            "target": self.target_certificate_digest,
            "reason": self.reason,
            "revoked_by": self.revoked_by,
            # Stamped once in __init__: every to_dict() must agree,
            # or two digests of one revocation would differ.
            "revoked_at": self.revoked_at,
            "version": "0.1.0",
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def sign(self) -> dict[str, Any]:
        """Sign this revocation using the configured Ed25519 key.

        Returns the in-toto style signed statement as produced by
        evidence.signing.sign_statement. Raises SigningError if the
        signing key is not configured.
        """
        from evidence.signing import sign_statement

        return sign_statement(self.to_dict())


class RejectionNotice:
    """Written instead of a certificate when verification is not complete."""

    def __init__(
        self,
        repository: str,
        commit_sha: str,
        requirements_digest: str,
        verified_contracts: int,
        unverified_contracts: int,
        failed_contracts: int,
        reasons: list[str],
        extension: dict[str, Any] | None = None,
    ) -> None:
        self.subject = {"repository": repository, "commit_sha": commit_sha}
        self.requirements_digest = requirements_digest
        self.verified_contracts = verified_contracts
        self.unverified_contracts = unverified_contracts
        self.failed_contracts = failed_contracts
        self.reasons = reasons
        self.extension = dict(extension or {})
        self.issued_at = datetime.now(UTC).isoformat()
        self.issuer = "SpecProof"
        self.version = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        document = {
            "subject": self.subject,
            "requirements_digest": self.requirements_digest,
            "result": "REJECTED",
            "verified_contracts": self.verified_contracts,
            "unverified_contracts": self.unverified_contracts,
            "failed_contracts": self.failed_contracts,
            "reasons": self.reasons,
            "issued_at": self.issued_at,
            "issuer": self.issuer,
            "version": self.version,
        }
        if self.extension:
            document["extension"] = dict(self.extension)
        return document

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _requirements_digest(requirements_text: str) -> str:
    return "sha256:" + hashlib.sha256(requirements_text.encode()).hexdigest()


def issue_certificate(
    repository: str,
    commit_sha: str,
    requirements_text: str,
    contracts: list[dict[str, Any]],
    evidence_digests: list[str] | None = None,
    extension: dict[str, Any] | None = None,
) -> MergeCertificate | None:
    """Issue a Merge Certificate only when every contract passed with evidence.

    Returns None (and callers must write a RejectionNotice) otherwise.
    """
    decision = evaluate_verification(
        {"rows": contracts}, contracts=contracts, require_experiment=False,
    )
    if decision.status != "VERIFIED":
        return None

    recorded_evidence = sorted({
        ref for contract in contracts for ref in evidence_references(contract)
    } | set(evidence_digests or []))

    return MergeCertificate(
        repository=repository,
        commit_sha=commit_sha,
        requirements_digest=_requirements_digest(requirements_text),
        verified_contracts=decision.passed,
        evidence_digests=recorded_evidence,
        toolchain={
            "specproof_version": "0.1.0",
            "python": "3.12",
        },
        extension=extension,
    )


def build_rejection_notice(
    repository: str,
    commit_sha: str,
    requirements_text: str,
    contracts: list[dict[str, Any]],
    reasons: list[str],
    extension: dict[str, Any] | None = None,
) -> RejectionNotice:
    """Build the rejection notice written instead of a certificate."""
    return RejectionNotice(
        repository=repository,
        commit_sha=commit_sha,
        requirements_digest=_requirements_digest(requirements_text),
        verified_contracts=sum(1 for c in contracts if c.get("result") == "PASS"),
        unverified_contracts=sum(1 for c in contracts if c.get("result") not in ("PASS", "FAIL")),
        failed_contracts=sum(1 for c in contracts if c.get("result") == "FAIL"),
        reasons=reasons,
        extension=extension,
    )
