"""Merge Certificate — cryptographic attestation of verification results."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


class MergeCertificate:
    """Represents a signed verification certificate.

    Follows in-toto Statement style. Binds commit SHA, requirement version,
    and evidence hashes.
    """

    def __init__(
        self,
        repository: str,
        commit_sha: str,
        requirements_digest: str,
        verified_contracts: int,
        unverified_contracts: int,
        evidence_digests: list[str],
        toolchain: dict[str, str],
    ) -> None:
        self.subject = {
            "repository": repository,
            "commit_sha": commit_sha,
        }
        self.requirements_digest = requirements_digest
        self.verified_contracts = verified_contracts
        self.unverified_contracts = unverified_contracts
        self.evidence_digests = evidence_digests
        self.toolchain = toolchain
        self.issued_at = datetime.now(UTC).isoformat()
        self.issuer = "SpecProof"
        self.version = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "requirements_digest": self.requirements_digest,
            "result": "VERIFIED" if self.unverified_contracts == 0 else "BLOCKED",
            "verified_contracts": self.verified_contracts,
            "unverified_contracts": self.unverified_contracts,
            "evidence_digests": self.evidence_digests,
            "toolchain": self.toolchain,
            "issued_at": self.issued_at,
            "issuer": self.issuer,
            "version": self.version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def signature_payload(self) -> bytes:
        """Return canonical bytes for signing (Ed25519 in Phase 1+)."""
        return self.to_json().encode("utf-8")


def issue_certificate(
    repository: str,
    commit_sha: str,
    requirements_text: str,
    contracts: list[dict],
    evidence_digests: list[str] | None = None,
) -> MergeCertificate:
    """Create a Merge Certificate for a verified PR.

    Phase 0 uses SHA-256 hashes; Phase 1+ adds Ed25519 signatures.
    """
    req_digest = "sha256:" + hashlib.sha256(requirements_text.encode()).hexdigest()
    verified = sum(1 for c in contracts if c.get("result") == "PASS")
    unverified = sum(1 for c in contracts if c.get("result") != "PASS")

    return MergeCertificate(
        repository=repository,
        commit_sha=commit_sha,
        requirements_digest=req_digest,
        verified_contracts=verified,
        unverified_contracts=unverified,
        evidence_digests=evidence_digests or [],
        toolchain={
            "specproof_version": "0.1.0",
            "python": "3.12",
        },
    )
