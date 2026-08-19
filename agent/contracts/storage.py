"""Backend seam for the contract registry (industrialization §A task 6).

One protocol, two interchangeable backends:

- ``MySQLContractStorage`` — durable production storage (single-cursor
  execute-then-fetch discipline per CLAUDE.md). Append-only by schema:
  contract_registry carries a composite PRIMARY KEY (id, version), so an
  in-place version bump is impossible at the SQL level.
- ``InMemoryContractStorage`` — the same semantics for unit tests,
  no Docker / no network.

The registry (agent/contracts/registry.py) owns ALL versioning and
approval semantics; backends only persist rows and perform the CAS status
update on an exact (contract_id, version). Backends provide no content
UPDATE path by construction — mutation of a stored version is impossible
at this seam and raises ContractVersionError at the registry seam.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Protocol, cast

from storage.mysql import MySQLStore


class DuplicateVersionError(RuntimeError):
    """A row for this exact (contract_id, version) already exists."""


#: Persisted content columns of one stored version. These columns — and
#: only these — participate in change detection; forbidden_changes is
#: pipeline-local data compiled from the spec each run, never registry
#: content.
PERSISTED_CONTENT_COLUMNS = (
    "checker_type",
    "requirement",
    "requirement_ref",
    "expected_behavior",
    "checker_version",
    "spec_digest",
)


class ContractStorage(Protocol):
    """Persistence seam the registry semantics run against."""

    def insert_version(self, row: Mapping[str, Any]) -> None:
        """Append a NEW (contract_id, version). Raises DuplicateVersionError
        when that exact version already exists — append-only, never an
        upsert."""
        ...

    def list_rows(
        self, repo_path: str, status: str | None = None,
    ) -> list[dict[str, Any]]:
        """All stored versions for a repository, newest first."""
        ...

    def get_row(self, contract_id: str, version: int) -> dict[str, Any] | None:
        """The exact stored version, or None."""
        ...

    def versions_of(self, contract_id: str) -> list[dict[str, Any]]:
        """All stored versions of one contract, ascending by version."""
        ...

    def cas_status(self, contract_id: str, version: int, action: str) -> bool:
        """CAS the status of ONE exact version (action: APPROVE/REJECT/
        REVOKE). Returns True when exactly one row changed. This is the
        only UPDATE any backend implements."""
        ...

    def record_approval(
        self,
        contract_id: str,
        version: int,
        action: str,
        approved_by: str,
        reason: str,
    ) -> None:
        """Append an audit row binding (contract_id, version) to the action."""
        ...

    def approval_rows(self) -> list[dict[str, Any]]:
        """Audit rows, oldest first (tests + audit reporting)."""
        ...

    def approved_rows(
        self, repo_path: str, spec_digest: str,
    ) -> list[dict[str, Any]]:
        """Approved versions for (repo, spec digest), newest version first."""
        ...


# ── MySQL backend ─────────────────────────────────────────────────────────


# Fully static statements only: every value travels through a placeholder,
# and the status literals are fixed per action (bandit B608 stays quiet).
_INSERT_VERSION_SQL = (
    "INSERT INTO contract_registry "
    "(id, repo_path, requirement_ref, requirement, checker_type, "
    "expected_behavior, source, version, status, spec_digest, "
    "checker_version) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)

_LIST_ROWS_SQL = (
    "SELECT * FROM contract_registry WHERE repo_path = %s "
    "ORDER BY created_at DESC, id, version DESC"
)

_LIST_ROWS_STATUS_SQL = (
    "SELECT * FROM contract_registry "
    "WHERE repo_path = %s AND status = %s "
    "ORDER BY created_at DESC, id, version DESC"
)

_GET_ROW_SQL = (
    "SELECT * FROM contract_registry WHERE id = %s AND version = %s"
)

_VERSIONS_OF_SQL = (
    "SELECT * FROM contract_registry WHERE id = %s ORDER BY version"
)

_APPROVE_SQL = (
    "UPDATE contract_registry SET status = 'APPROVED' "
    "WHERE id = %s AND version = %s AND status IN ('PROPOSED', 'REJECTED')"
)

_REJECT_SQL = (
    "UPDATE contract_registry SET status = 'REJECTED' "
    "WHERE id = %s AND version = %s AND status IN ('PROPOSED')"
)

_REVOKE_SQL = (
    "UPDATE contract_registry SET status = 'REVOKED' "
    "WHERE id = %s AND version = %s AND status IN ('APPROVED')"
)

_CAS_BY_ACTION: dict[str, str] = {
    "APPROVE": _APPROVE_SQL,
    "REJECT": _REJECT_SQL,
    "REVOKE": _REVOKE_SQL,
}

_INSERT_APPROVAL_SQL = (
    "INSERT INTO contract_approvals "
    "(contract_id, contract_version, action, approved_by, reason) "
    "VALUES (%s, %s, %s, %s, %s)"
)

_APPROVAL_ROWS_SQL = (
    "SELECT contract_id, contract_version, action, approved_by, reason, "
    "created_at FROM contract_approvals ORDER BY id"
)

_APPROVED_ROWS_SQL = (
    "SELECT * FROM contract_registry "
    "WHERE repo_path = %s AND status = 'APPROVED' AND spec_digest = %s "
    "ORDER BY version DESC"
)


class MySQLContractStorage:
    """Production backend over MySQLStore (migrations 0001 + 0006)."""

    def __init__(self, store: MySQLStore) -> None:
        self.store = store

    def insert_version(self, row: Mapping[str, Any]) -> None:
        params = (
            str(row["id"]),
            str(row.get("repo_path") or ""),
            str(row.get("requirement_ref") or ""),
            str(row.get("requirement") or ""),
            str(row.get("checker_type") or ""),
            str(row.get("expected_behavior") or ""),
            str(row.get("source") or "spec"),
            int(row.get("version") or 1),
            str(row.get("status") or "PROPOSED"),
            str(row.get("spec_digest") or ""),
            str(row.get("checker_version") or ""),
        )
        try:
            with self.store.connection() as conn:
                conn.cursor().execute(_INSERT_VERSION_SQL, params)
        except Exception as exc:
            if _is_duplicate_key(exc):
                raise DuplicateVersionError(
                    "contract version ("
                    + str(row.get("id"))
                    + ", "
                    + str(row.get("version"))
                    + ") already exists",
                ) from exc
            raise

    def list_rows(
        self, repo_path: str, status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            cur = conn.cursor()
            if status:
                cur.execute(_LIST_ROWS_STATUS_SQL, (repo_path, status))
            else:
                cur.execute(_LIST_ROWS_SQL, (repo_path,))
            return list(cur.fetchall())

    def get_row(self, contract_id: str, version: int) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute(_GET_ROW_SQL, (contract_id, version))
            return cast(dict[str, Any] | None, cur.fetchone())

    def versions_of(self, contract_id: str) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute(_VERSIONS_OF_SQL, (contract_id,))
            return list(cur.fetchall())

    def cas_status(self, contract_id: str, version: int, action: str) -> bool:
        sql = _CAS_BY_ACTION[action]
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (contract_id, version))
            return bool(cur.rowcount == 1)

    def record_approval(
        self,
        contract_id: str,
        version: int,
        action: str,
        approved_by: str,
        reason: str,
    ) -> None:
        with self.store.connection() as conn:
            conn.cursor().execute(
                _INSERT_APPROVAL_SQL,
                (contract_id, version, action, approved_by, reason),
            )

    def approval_rows(self) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute(_APPROVAL_ROWS_SQL)
            return list(cur.fetchall())

    def approved_rows(
        self, repo_path: str, spec_digest: str,
    ) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            cur = conn.cursor()
            cur.execute(_APPROVED_ROWS_SQL, (repo_path, spec_digest))
            return list(cur.fetchall())


def _is_duplicate_key(exc: Exception) -> bool:
    """Best-effort duplicate-key detection (no driver-specific imports).

    MySQL reports ER_DUP_ENTRY as 1062 inside args[0]; SQLite reports
    "UNIQUE constraint failed" in args[0] text. Anything else is re-raised.
    """
    first = exc.args[0] if exc.args else ""
    if first == 1062:
        return True
    text = str(first)
    return "UNIQUE constraint failed" in text or "Duplicate entry" in text

# ── In-memory backend ─────────────────────────────────────────────────────


class InMemoryContractStorage:
    """Thread-safe in-memory backend with MySQLContractStorage semantics.

    Used by unit tests (no Docker / no network) to exercise the real
    registry code paths — propose/approve/version resolution run on the
    same seam the production backend implements.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._rows: dict[tuple[str, int], dict[str, Any]] = {}
        self._approvals: list[dict[str, Any]] = []

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def insert_version(self, row: Mapping[str, Any]) -> None:
        key = (str(row["id"]), int(row.get("version") or 1))
        with self._lock:
            if key in self._rows:
                raise DuplicateVersionError(
                    f"contract version {key} already exists"
                )
            stored = dict(row)
            stored.setdefault("created_at", self._now())
            stored.setdefault("updated_at", stored["created_at"])
            self._rows[key] = stored

    def list_rows(
        self, repo_path: str, status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                r for (_cid, _v), r in self._rows.items()
                if r.get("repo_path") == repo_path
            ]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        return sorted(
            rows,
            key=lambda r: (-int(r.get("version") or 0),),
        )

    def get_row(self, contract_id: str, version: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._rows.get((contract_id, version))
            return dict(row) if row is not None else None

    def versions_of(self, contract_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                r for (cid, _v), r in self._rows.items() if cid == contract_id
            ]
        return sorted(rows, key=lambda r: int(r.get("version") or 0))

    def cas_status(self, contract_id: str, version: int, action: str) -> bool:
        allowed = {
            "APPROVE": {"PROPOSED", "REJECTED"},
            "REJECT": {"PROPOSED"},
            "REVOKE": {"APPROVED"},
        }[action]
        new_status = {
            "APPROVE": "APPROVED",
            "REJECT": "REJECTED",
            "REVOKE": "REVOKED",
        }[action]
        with self._lock:
            row = self._rows.get((contract_id, version))
            if row is None or row.get("status") not in allowed:
                return False
            if row.get("status") == new_status:
                return False
            row["status"] = new_status
            row["updated_at"] = self._now()
            return True

    def record_approval(
        self,
        contract_id: str,
        version: int,
        action: str,
        approved_by: str,
        reason: str,
    ) -> None:
        with self._lock:
            self._approvals.append({
                "contract_id": contract_id,
                "contract_version": version,
                "action": action,
                "approved_by": approved_by,
                "reason": reason,
                "created_at": self._now(),
            })

    def approval_rows(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._approvals]

    def approved_rows(
        self, repo_path: str, spec_digest: str,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                r for (_cid, _v), r in self._rows.items()
                if r.get("repo_path") == repo_path
                and r.get("status") == "APPROVED"
                and r.get("spec_digest") == spec_digest
            ]
        return sorted(rows, key=lambda r: -int(r.get("version") or 0))


__all__ = [
    "PERSISTED_CONTENT_COLUMNS",
    "ContractStorage",
    "DuplicateVersionError",
    "InMemoryContractStorage",
    "MySQLContractStorage",
]
