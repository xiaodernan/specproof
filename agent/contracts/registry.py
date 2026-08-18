"""P2 — Contract approval registry (human approval workflow).

The registry is the boundary between "candidate" (a proposal extracted
from a spec or repository constitution) and "contract" (an enforceable
rule the verification pipeline may rely on).

Storage: MySQL contract_registry + contract_approvals tables.
Without MySQL the registry raises honestly — approvals are durable
business state and must never degrade to in-memory guesses.
"""

from __future__ import annotations

from typing import Any

from agent.contracts.compiler import ContractCandidate
from storage.mysql import MySQLStore


class ContractRegistry:
    """Durable store for proposed/approved contracts."""

    def __init__(self, store: MySQLStore | None = None) -> None:
        self.store = store or MySQLStore()

    # ── Proposals ─────────────────────────────────────────────

    def upsert_candidates(
        self,
        repo_path: str,
        spec_digest: str,
        candidates: list[ContractCandidate],
    ) -> int:
        """Insert candidates as PROPOSED. Existing rows keep their status
        (re-proposing does not silently un-approve an approved contract),
        but behaviour/version are refreshed when the spec changed.

        Returns the number of rows written.
        """
        written = 0
        proposed = "PROPOSED"
        for c in candidates:
            with self.store.connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT version, status, spec_digest FROM contract_registry "
                    "WHERE id = %s",
                    (c.id,),
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        "INSERT INTO contract_registry "
                        "(id, repo_path, requirement_ref, requirement, "
                        "checker_type, expected_behavior, source, version, "
                        "status, spec_digest) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s)",
                        (
                            c.id, repo_path, c.requirement_ref, c.requirement,
                            c.checker_type, c.expected_behavior, c.source,
                            proposed, spec_digest,
                        ),
                    )
                    written += 1
                elif row["spec_digest"] != spec_digest:
                    cur.execute(
                        "UPDATE contract_registry SET version = version + 1, "
                        "expected_behavior = %s, requirement_ref = %s, "
                        "checker_type = %s, spec_digest = %s WHERE id = %s",
                        (
                            c.expected_behavior, c.requirement_ref,
                            c.checker_type, spec_digest, c.id,
                        ),
                    )
                    written += 1
        return written

    def list_contracts(
        self, repo_path: str, status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List registry rows for a repository, newest first."""
        with self.store.connection() as conn:
            cur = conn.cursor()
            if status:
                cur.execute(
                    "SELECT * FROM contract_registry "
                    "WHERE repo_path = %s AND status = %s "
                    "ORDER BY created_at DESC, id",
                    (repo_path, status),
                )
            else:
                cur.execute(
                    "SELECT * FROM contract_registry WHERE repo_path = %s "
                    "ORDER BY created_at DESC, id",
                    (repo_path,),
                )
            return list(cur.fetchall())

    # ── Approval workflow ─────────────────────────────────────

    def _record_approval(
        self, contract_id: str, action: str, approved_by: str, reason: str,
    ) -> None:
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO contract_approvals "
                "(contract_id, action, approved_by, reason) "
                "VALUES (%s, %s, %s, %s)",
                (contract_id, action, approved_by, reason),
            )

    def _set_status(
        self,
        contract_id: str,
        new_status: str,
        allowed_from: tuple[str, ...],
        action: str,
        approved_by: str,
        reason: str,
    ) -> bool:
        """CAS-style status update + approval audit row."""
        placeholders = ", ".join(["%s"] * len(allowed_from))
        with self.store.connection() as conn:
            cur = conn.cursor()
            # B608 false positive: every value is a bound parameter (%s);
            # the only dynamic part is the placeholder count, derived from
            # a trusted literal tuple (allowed_from).
            cur.execute(
                "UPDATE contract_registry SET status = %s "  # nosec
                "WHERE id = %s AND status IN (" + placeholders + ")",
                (new_status, contract_id, *allowed_from),
            )
            changed = cur.rowcount
        if changed:
            self._record_approval(contract_id, action, approved_by, reason)
        return bool(changed)

    def approve(
        self, contract_id: str, approved_by: str, reason: str = "",
    ) -> bool:
        """Approve a proposed (or previously rejected) contract."""
        return self._set_status(
            contract_id, "APPROVED", ("PROPOSED", "REJECTED"),
            "APPROVE", approved_by, reason,
        )

    def reject(
        self, contract_id: str, approved_by: str, reason: str = "",
    ) -> bool:
        """Reject a proposed contract (stays visible for the audit trail)."""
        return self._set_status(
            contract_id, "REJECTED", ("PROPOSED",),
            "REJECT", approved_by, reason,
        )

    def revoke(
        self, contract_id: str, approved_by: str, reason: str = "",
    ) -> bool:
        """Revoke an approved contract."""
        return self._set_status(
            contract_id, "REVOKED", ("APPROVED",),
            "REVOKE", approved_by, reason,
        )

    # ── Read path used by the verification pipeline ───────────

    def get_approved_for_repo(
        self, repo_path: str, spec_digest: str,
    ) -> list[ContractCandidate]:
        """Approved contracts for the CURRENT spec version only.

        Contracts approved against an older spec_digest are not returned:
        the approval does not transfer when the requirement changed.
        """
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, checker_type, requirement, requirement_ref, "
                "expected_behavior, source, spec_digest "
                "FROM contract_registry "
                "WHERE repo_path = %s AND status = %s "
                "AND spec_digest = %s",
                (repo_path, "APPROVED", spec_digest),
            )
            rows = cur.fetchall()
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
            )
            for r in rows
        ]
