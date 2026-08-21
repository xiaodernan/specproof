"""Immutable contract version records (industrialization §A task 6).

One ``ContractRecord`` is the durable projection of ONE stored version of a
contract. The registry is append-only per ``(contract_id, version)``:

- a version, once stored, never mutates — edits create a NEW version;
- approvals / rejections / revocations bind to an exact
  ``(contract_id, version)`` and are the only permitted later write
  (a CAS status transition, audit-logged);
- every attempt to mutate a stored version raises ``ContractVersionError``.

Each compiled contract also carries the implementation version of the
checker that produced it (``checker_version``), resolved from the declaring
checker module's ``__version__`` if present, else its declared
``CHECKER_VERSION`` constant, else the stable ``DEFAULT_CHECKER_VERSION``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Statuses a stored version may carry (registry lifecycle).
CONTRACT_STATUSES = ("PROPOSED", "APPROVED", "REJECTED", "REVOKED")

#: Stable fallback when a checker module declares neither __version__ nor
#: CHECKER_VERSION — never guessed, always the same literal.
DEFAULT_CHECKER_VERSION = "unversioned"

#: checker_type -> checker module that implements its deterministic rules.
_CHECKER_MODULES: dict[str, str] = {
    "http": "agent.checkers.java_source",
    "sql": "agent.checkers.java_source",
    "redis": "agent.checkers.java_source",
    "openapi": "agent.checkers.java_source",
    "rabbitmq": "agent.checkers.java_source",
    "constitution": "agent.checkers.constitution",
    "tests": "agent.checkers.schema_and_tests",
    "schema": "agent.checkers.schema_and_tests",
}


class ContractVersionError(RuntimeError):
    """Raised when an operation would mutate a stored contract version."""


def checker_version_for(checker_type: str) -> str:
    """The implementation version of the checker for *checker_type*.

    Resolution order (stable, documented): module ``__version__`` when
    present, else the declared ``CHECKER_VERSION`` constant, else
    ``DEFAULT_CHECKER_VERSION``. Import failures degrade to the default
    rather than raising — version stamping must never break compilation.
    """
    module_name = _CHECKER_MODULES.get(checker_type)
    if module_name is None:
        return DEFAULT_CHECKER_VERSION
    try:
        module = importlib.import_module(module_name)
    except Exception:  # noqa: BLE001 — stamping must never break compilation
        return DEFAULT_CHECKER_VERSION
    declared = getattr(module, "__version__", None)
    if declared is None:
        declared = getattr(module, "CHECKER_VERSION", None)
    return str(declared) if declared else DEFAULT_CHECKER_VERSION


@dataclass(frozen=True)
class ContractRecord:
    """Durable, immutable projection of one stored contract version."""

    contract_id: str
    version: int = 1
    checker_version: str = DEFAULT_CHECKER_VERSION
    checker_type: str = ""
    requirement: str = ""
    requirement_ref: str = ""
    expected_behavior: str = ""
    forbidden_changes: tuple[str, ...] = ()
    source: str = "spec"
    spec_digest: str = ""
    status: str = "PROPOSED"
    repo_path: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ContractVersionError(
                f"contract version must be >= 1, got {self.version}"
            )
        if self.status not in CONTRACT_STATUSES:
            raise ContractVersionError(
                f"unknown contract status {self.status!r}; "
                f"expected one of {CONTRACT_STATUSES}"
            )

    # ── content snapshot ──────────────────────────────────────────

    def content_fields(self) -> dict[str, Any]:
        """The immutable content of this version (everything but status/
        timestamps). Content equality is defined over exactly this dict."""
        return {
            "contract_id": self.contract_id,
            "version": self.version,
            "checker_version": self.checker_version,
            "checker_type": self.checker_type,
            "requirement": self.requirement,
            "requirement_ref": self.requirement_ref,
            "expected_behavior": self.expected_behavior,
            "forbidden_changes": list(self.forbidden_changes),
            "source": self.source,
            "spec_digest": self.spec_digest,
        }

    def content_key(self) -> str:
        """Canonical-JSON digest over the immutable content fields."""
        return hashlib.sha256(
            json.dumps(
                self.content_fields(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def content_equal(self, other: ContractRecord) -> bool:
        """True when the two records carry identical immutable content."""
        return self.content_key() == other.content_key()

    # ── projections ───────────────────────────────────────────────

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ContractRecord:
        """Build a record from a registry row / candidate mapping."""
        forbidden = row.get("forbidden_changes") or []
        if isinstance(forbidden, str):
            forbidden = [forbidden]
        return cls(
            contract_id=str(row.get("id") or row.get("contract_id") or ""),
            version=int(row.get("version") or 1),
            checker_version=str(row.get("checker_version") or DEFAULT_CHECKER_VERSION),
            checker_type=str(row.get("checker_type") or ""),
            requirement=str(row.get("requirement") or ""),
            requirement_ref=str(row.get("requirement_ref") or ""),
            expected_behavior=str(row.get("expected_behavior") or ""),
            forbidden_changes=tuple(str(c) for c in forbidden),
            source=str(row.get("source") or "spec"),
            spec_digest=str(row.get("spec_digest") or ""),
            status=str(row.get("status") or "PROPOSED"),
            repo_path=str(row.get("repo_path") or ""),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    def to_candidate(self) -> Any:
        """Project this stored version onto a ContractCandidate.

        Deferred import keeps this module free of a compiler import cycle.
        """
        from agent.contracts.compiler import ContractCandidate

        return ContractCandidate(
            id=self.contract_id,
            checker_type=self.checker_type,
            requirement=self.requirement,
            requirement_ref=self.requirement_ref,
            expected_behavior=self.expected_behavior,
            forbidden_changes=list(self.forbidden_changes),
            source=self.source,
            result="UNVERIFIED",
            approved=self.status == "APPROVED",
            version=self.version,
            checker_version=self.checker_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict projection (registry rows / lineage meta)."""
        return {
            "id": self.contract_id,
            "version": self.version,
            "checker_version": self.checker_version,
            "checker_type": self.checker_type,
            "requirement": self.requirement,
            "requirement_ref": self.requirement_ref,
            "expected_behavior": self.expected_behavior,
            "forbidden_changes": list(self.forbidden_changes),
            "source": self.source,
            "spec_digest": self.spec_digest,
            "status": self.status,
            "repo_path": self.repo_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


__all__ = [
    "CONTRACT_STATUSES",
    "DEFAULT_CHECKER_VERSION",
    "ContractRecord",
    "ContractVersionError",
    "checker_version_for",
]
