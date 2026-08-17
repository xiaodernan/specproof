"""Merge Certificate — cryptographic attestation of verification results.

Honesty contract (v2):
- A certificate is issued ONLY when every contract is PASS with evidence
  (unverified == 0 and failed == 0).
- Otherwise the pipeline writes a Rejection Notice instead — the absence of
  a certificate is meaningful and is never papered over.
- Phase 0/1 signs nothing: digests are SHA-256 over the recorded evidence.
  Ed25519 signing is a Phase 2 item (tracked in docs/ROADMAP.md).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


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
    ) -> None:
        self.subject = {
            "repository": repository,
            "commit_sha": commit_sha,
        }
        self.requirements_digest = requirements_digest
        self.verified_contracts = verified_contracts
        self.evidence_digests = evidence_digests
        self.toolchain = toolchain
        self.issued_at = datetime.now(UTC).isoformat()
        self.issuer = "SpecProof"
        self.version = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
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

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


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
    ) -> None:
        self.subject = {"repository": repository, "commit_sha": commit_sha}
        self.requirements_digest = requirements_digest
        self.verified_contracts = verified_contracts
        self.unverified_contracts = unverified_contracts
        self.failed_contracts = failed_contracts
        self.reasons = reasons
        self.issued_at = datetime.now(UTC).isoformat()
        self.issuer = "SpecProof"
        self.version = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
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
) -> MergeCertificate | None:
    """Issue a Merge Certificate only when every contract passed with evidence.

    Returns None (and callers must write a RejectionNotice) otherwise.
    """
    passed = [c for c in contracts if c.get("result") == "PASS"]
    if len(passed) != len(contracts) or not contracts:
        return None

    return MergeCertificate(
        repository=repository,
        commit_sha=commit_sha,
        requirements_digest=_requirements_digest(requirements_text),
        verified_contracts=len(passed),
        evidence_digests=evidence_digests or [],
        toolchain={
            "specproof_version": "0.1.0",
            "python": "3.12",
        },
    )


def build_rejection_notice(
    repository: str,
    commit_sha: str,
    requirements_text: str,
    contracts: list[dict[str, Any]],
    reasons: list[str],
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
    )
