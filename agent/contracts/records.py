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


def patterns_from_cell(value: Any) -> tuple[str, ...]:
    """The declared key families as they come back from storage.

    The column is JSON, but a driver may hand it back as a string, and a
    hand-made row may carry a plain list — all three say the same thing.
    A value that cannot be read yields an EMPTY tuple: "this version
    declared nothing we can see" is not "it declared keys".
    """
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        try:
            value = json.loads(text)
        except ValueError:
            return (text,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


@dataclass(frozen=True)
class ContractRecord:
    """Durable, immutable projection of one stored contract version.

    Phase 1 extensions (P1-3): certificate/capsule/evidence references,
    lineage bloodline, evidence minimum, and waiver fields. These are
    *metadata* (not content-equality fields) except ``evidence_minimum``
    and ``supersedes``/``parent_version`` which affect content identity.
    """

    contract_id: str
    version: int = 1
    checker_version: str = DEFAULT_CHECKER_VERSION
    checker_type: str = ""
    requirement: str = ""
    requirement_ref: str = ""
    expected_behavior: str = ""
    forbidden_changes: tuple[str, ...] = ()
    #: The key families this version DECLARED ("observes keys: …"), kept
    #: with the version so an APPROVED contract keeps the declaration it
    #: was approved with (the spec digest already covers "the spec
    #: changed", so this is not a change-detection column).
    observes_keys: tuple[str, ...] = ()
    source: str = "spec"
    spec_digest: str = ""
    status: str = "PROPOSED"
    repo_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    # ── Phase 1: certificate / capsule / evidence references ──
    certificate_digest: str = ""       # sha256 of the issued Merge Certificate
    capsule_ref: str = ""              # MinIO object reference for the Bug Capsule
    evidence_pack_ref: str = ""        # MinIO/DB reference for the Evidence Pack
    # ── Phase 1: lineage bloodline ──
    supersedes: str = ""               # contract_id this version replaces
    parent_version: int = 0            # version number of the parent contract
    lineage_root: str = ""             # digest root of the evidence DAG
    # ── Phase 1: evidence policy ──
    evidence_minimum: str = "STATIC"   # STATIC | DYNAMIC | DB_STATE
    # ── Phase 1: waiver ──
    waiver: bool = False
    waiver_reason: str = ""
    waived_by: str = ""
    waived_at: str = ""
    waiver_expires_at: str = ""

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
        timestamps). Content equality is defined over exactly this dict.

        Phase 1: ``evidence_minimum``, ``supersedes``, ``parent_version``
        are content fields — changing them creates a new version.
        Certificate/capsule/evidence/waiver fields are metadata only.
        """
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
            "evidence_minimum": self.evidence_minimum,
            "supersedes": self.supersedes,
            "parent_version": self.parent_version,
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
            observes_keys=patterns_from_cell(row.get("observes_keys")),
            source=str(row.get("source") or "spec"),
            spec_digest=str(row.get("spec_digest") or ""),
            status=str(row.get("status") or "PROPOSED"),
            repo_path=str(row.get("repo_path") or ""),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
            # Phase 1 fields
            certificate_digest=str(row.get("certificate_digest") or ""),
            capsule_ref=str(row.get("capsule_ref") or ""),
            evidence_pack_ref=str(row.get("evidence_pack_ref") or ""),
            supersedes=str(row.get("supersedes") or ""),
            parent_version=int(row.get("parent_version") or 0),
            lineage_root=str(row.get("lineage_root") or ""),
            evidence_minimum=str(row.get("evidence_minimum") or "STATIC"),
            waiver=bool(row.get("waiver") or False),
            waiver_reason=str(row.get("waiver_reason") or ""),
            waived_by=str(row.get("waived_by") or ""),
            waived_at=str(row.get("waived_at") or ""),
            waiver_expires_at=str(row.get("waiver_expires_at") or ""),
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
            observes_keys=list(self.observes_keys),
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
            "observes_keys": list(self.observes_keys),
            "source": self.source,
            "spec_digest": self.spec_digest,
            "status": self.status,
            "repo_path": self.repo_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            # Phase 1 fields
            "certificate_digest": self.certificate_digest,
            "capsule_ref": self.capsule_ref,
            "evidence_pack_ref": self.evidence_pack_ref,
            "supersedes": self.supersedes,
            "parent_version": self.parent_version,
            "lineage_root": self.lineage_root,
            "evidence_minimum": self.evidence_minimum,
            "waiver": self.waiver,
            "waiver_reason": self.waiver_reason,
            "waived_by": self.waived_by,
            "waived_at": self.waived_at,
            "waiver_expires_at": self.waiver_expires_at,
        }


__all__ = [
    "CONTRACT_STATUSES",
    "DEFAULT_CHECKER_VERSION",
    "ContractRecord",
    "ContractVersionError",
    "checker_version_for",
]
