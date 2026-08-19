"""P2 — Contract approval registry (human approval workflow).

§A task 6 (immutable versioning):

- the registry is append-only per (contract_id, version): proposing
  INSERTs a new version and never UPDATEs stored content;
- approvals / rejections / revocations bind to an exact
  (contract_id, version) — the audit row records the version and the CAS
  status transition targets one version row;
- any attempt to mutate a stored version raises ContractVersionError;
- every stored version carries checker_version — the implementation
  version of the checker that produced it.

Storage: MySQL via MySQLContractStorage (migrations 0001 + 0006).
Without MySQL the registry raises honestly — approvals are durable
business state and must never degrade to in-memory guesses. Unit tests
exercise the identical semantics on InMemoryContractStorage (no Docker).
"""

from __future__ import annotations

from typing import Any

from agent.contracts.compiler import ContractCandidate
from agent.contracts.records import ContractRecord, ContractVersionError, checker_version_for
from agent.contracts.storage import (
    PERSISTED_CONTENT_COLUMNS,
    ContractStorage,
    DuplicateVersionError,
    MySQLContractStorage,
)
from storage.mysql import MySQLStore


class ContractRegistry:
    """Durable, append-only store for proposed/approved contracts."""

    def __init__(self, storage: ContractStorage | None = None) -> None:
        if storage is None:
            storage = MySQLContractStorage(MySQLStore())
        self.storage = storage

    # ── Proposals (append-only) ────────────────────────────────

    def upsert_candidates(
        self,
        repo_path: str,
        spec_digest: str,
        candidates: list[ContractCandidate],
    ) -> int:
        """Propose candidates as PROPOSED — append-only versioning.

        - first proposal of a contract id inserts version 1;
        - identical content for the SAME spec digest is an idempotent
          no-op (an approved version keeps its status — re-proposing
          never silently un-approves);
        - changed content or a changed spec digest APPENDS a new version
          (version + 1) as PROPOSED: edits create a NEW version, they
          never mutate a stored one, and approvals never auto-inherit.

        Returns the number of versions appended.
        """
        written = 0
        for c in candidates:
            if self._propose_one(repo_path, spec_digest, c):
                written += 1
        return written

    def _propose_one(
        self,
        repo_path: str,
        spec_digest: str,
        candidate: ContractCandidate,
    ) -> bool:
        snapshot = self._candidate_snapshot(repo_path, spec_digest, candidate)
        existing = self.storage.versions_of(candidate.id)
        if not existing:
            self._append({**snapshot, "version": 1, "status": "PROPOSED"}, candidate.id)
            return True
        latest = existing[-1]  # ascending by version
        if (
            str(latest.get("spec_digest") or "") == spec_digest
            and self._content_unchanged(latest, snapshot)
        ):
            return False  # idempotent re-propose of the same content
        self._append(
            {**snapshot, "version": int(latest["version"]) + 1, "status": "PROPOSED"},
            candidate.id,
        )
        return True

    @staticmethod
    def _content_unchanged(row: dict[str, Any], snapshot: dict[str, Any]) -> bool:
        """Content equality over the persisted column set only."""
        return all(
            (row.get(col) or "") == (snapshot.get(col) or "")
            for col in PERSISTED_CONTENT_COLUMNS
        )

    @staticmethod
    def _candidate_snapshot(
        repo_path: str,
        spec_digest: str,
        candidate: ContractCandidate,
    ) -> dict[str, Any]:
        return {
            "id": candidate.id,
            "repo_path": repo_path,
            "requirement_ref": candidate.requirement_ref,
            "requirement": candidate.requirement,
            "checker_type": candidate.checker_type,
            "expected_behavior": candidate.expected_behavior,
            "source": candidate.source,
            "spec_digest": spec_digest,
            "checker_version": (
                candidate.checker_version or checker_version_for(candidate.checker_type)
            ),
        }

    def _append(self, row: dict[str, Any], contract_id: str) -> None:
        """INSERT a new version; retry the next version number once when a
        concurrent writer appended the same one first."""
        try:
            self.storage.insert_version(row)
            return
        except DuplicateVersionError:
            rows = self.storage.versions_of(contract_id)
            next_version = int(rows[-1]["version"]) + 1 if rows else 1
            self.storage.insert_version({**row, "version": next_version})

    def list_contracts(
        self, repo_path: str, status: str | None = None,
    ) -> list[dict[str, Any]]:
        """All stored versions for a repository, newest first."""
        return self.storage.list_rows(repo_path, status)

    def list_versions(self, contract_id: str) -> list[ContractRecord]:
        """Every stored version of one contract, ascending by version."""
        return [
            ContractRecord.from_row(row)
            for row in self.storage.versions_of(contract_id)
        ]

    def get_contract_record(
        self, contract_id: str, version: int,
    ) -> ContractRecord | None:
        """The exact stored version, or None."""
        row = self.storage.get_row(contract_id, version)
        return ContractRecord.from_row(row) if row is not None else None

    # ── Approval workflow (binds exact versions) ───────────────

    def approve(
        self,
        contract_id: str,
        approved_by: str,
        reason: str = "",
        version: int | None = None,
    ) -> bool:
        """Approve an exact version (default: the newest stored version)."""
        return self._set_status(contract_id, "APPROVE", approved_by, reason, version)

    def reject(
        self,
        contract_id: str,
        approved_by: str,
        reason: str = "",
        version: int | None = None,
    ) -> bool:
        """Reject an exact proposed version (stays visible for the audit)."""
        return self._set_status(contract_id, "REJECT", approved_by, reason, version)

    def revoke(
        self,
        contract_id: str,
        approved_by: str,
        reason: str = "",
        version: int | None = None,
    ) -> bool:
        """Revoke an exact approved version."""
        return self._set_status(contract_id, "REVOKE", approved_by, reason, version)

    def _set_status(
        self,
        contract_id: str,
        action: str,
        approved_by: str,
        reason: str,
        version: int | None,
    ) -> bool:
        """CAS status transition on ONE exact version + audit row."""
        target = self._resolve_version(contract_id, version)
        if target is None:
            return False
        changed = self.storage.cas_status(contract_id, target, action)
        if changed:
            self.storage.record_approval(
                contract_id, target, action, approved_by, reason,
            )
        return changed

    def _resolve_version(
        self, contract_id: str, version: int | None,
    ) -> int | None:
        """Resolve the target version: explicit, or the newest stored one."""
        if version is not None:
            row = self.storage.get_row(contract_id, version)
            return version if row is not None else None
        rows = self.storage.versions_of(contract_id)
        return int(rows[-1]["version"]) if rows else None

    def approval_rows(self) -> list[dict[str, Any]]:
        """Approval audit rows (contract_id, contract_version) pairs."""
        return self.storage.approval_rows()

    # ── Immutability guard ─────────────────────────────────────

    def mutate_version(
        self, contract_id: str, version: int, **fields: Any,
    ) -> None:
        """Mutation of a stored version is forbidden — always raises.

        There is deliberately no content-update code path anywhere in the
        registry or its backends: edits must go through upsert_candidates,
        which appends a NEW version. This method exists so the invariant
        is enforced at the API surface too, not only by the absence of a
        write path.
        """
        raise ContractVersionError(
            f"contract version ({contract_id}, {version}) is immutable — "
            "stored versions never mutate; propose a new version instead "
            f"(rejected fields: {sorted(fields)})",
        )

    # ── Read path used by the verification pipeline ───────────

    def get_approved_for_repo(
        self, repo_path: str, spec_digest: str,
    ) -> list[ContractCandidate]:
        """Approved contracts for the CURRENT spec version only.

        Contracts approved against an older spec_digest are not returned:
        the approval does not transfer when the requirement changed.
        When several versions of one contract are approved, the newest
        approved version wins; each candidate carries its exact version
        and checker_version.
        """
        rows = self.storage.approved_rows(repo_path, spec_digest)
        seen: set[str] = set()
        newest: list[dict[str, Any]] = []
        for row in rows:  # already newest-version-first
            cid = str(row["id"])
            if cid in seen:
                continue
            seen.add(cid)
            newest.append(row)
        return [
            ContractCandidate(
                id=str(r["id"]),
                checker_type=str(r["checker_type"]),
                requirement=str(r["requirement"] or ""),
                requirement_ref=str(r["requirement_ref"] or ""),
                expected_behavior=str(r["expected_behavior"] or ""),
                source=str(r["source"] or "registry"),
                result="UNVERIFIED",
                approved=True,
                version=int(r.get("version") or 1),
                checker_version=str(r.get("checker_version") or ""),
            )
            for r in newest
        ]


__all__ = ["ContractRegistry"]
