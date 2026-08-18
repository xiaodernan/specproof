"""Durable, leaseable job store for SpecCraft agent jobs (Agent-Plan task 3).

One protocol, three interchangeable backends:

* 'InMemoryAgentJobStore' — development and tests;
* 'SqliteAgentJobStore' — file-based fallback; used by tests without Docker;
* 'MySqlAgentJobStore' — production (MySQL via PyMySQL, single-cursor
  execute-then-fetch discipline per CLAUDE.md).

'AgentJobStore' is the single source of truth for semantics: every backend
implements the same projection / lease / cancel rules, and both SQL backends
share one portable DDL and statement set ('?' placeholders, translated to
'%s' for PyMySQL; no MySQL-only DDL in the shared path). All timestamps are
epoch seconds and every backend accepts an injectable 'now_fn' clock so
lease-expiry semantics stay deterministic in tests. Every SQL statement is
fully static — all values travel through placeholders, never through SQL
text — and the terminal-status literals inside them are kept in sync with
the canonical status tuple by a consistency test.

Job record fields: id, status (pending/running/succeeded/failed/cancelled),
spec_text, spec_digest (sha256 hex), plan_json, current_step, progress_json,
lease_owner, lease_expires_at (epoch seconds), started_at, finished_at,
result_json, error, created_at, updated_at.

Wiring into craft/loop.py is out of scope here (that lane is owned by another
agent): see the "Integration note" comment block at the end of this file for
exactly where CraftLoop would call create / lease / renew / set_progress /
update_status / cancel.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from urllib.parse import unquote, urlsplit

import pymysql
from pymysql.cursors import DictCursor

JobStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]

JOB_STATUSES: tuple[JobStatus, ...] = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "cancelled",
)

_TERMINAL_STATUS_TUPLE: tuple[JobStatus, ...] = ("succeeded", "failed", "cancelled")
TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(_TERMINAL_STATUS_TUPLE)
_STATUS_VALUES: frozenset[str] = frozenset(JOB_STATUSES)

# The terminal-status literals inside the SQL statements below must match
# the tuple above; that invariant is enforced by
# TestSharedSqlConsistency (statements stay fully static for bandit B608 —
# every value travels through a placeholder, never through SQL text).


def compute_spec_digest(spec_text: str) -> str:
    """SHA-256 hex digest of the spec text — the stored 'spec_digest'."""
    return hashlib.sha256(spec_text.encode("utf-8")).hexdigest()


class AgentJobStoreError(RuntimeError):
    """Base error for all agent-job-store failures."""


class JobNotFoundError(AgentJobStoreError):
    """The requested agent job id does not exist."""


class JobAlreadyExistsError(AgentJobStoreError):
    """An agent job with this id was already created."""


class InvalidJobTransitionError(AgentJobStoreError):
    """The requested status transition is not allowed (terminal is final)."""


@dataclass(frozen=True)
class AgentJob:
    """Durable projection of one SpecCraft agent job."""

    id: str
    status: JobStatus
    spec_text: str
    spec_digest: str
    created_at: float
    updated_at: float
    plan_json: str | None = None
    current_step: str | None = None
    progress_json: str | None = None
    lease_owner: str | None = None
    lease_expires_at: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    result_json: str | None = None
    error: str | None = None


class AgentJobStore(Protocol):
    """Single source of truth for agent-job-store semantics (Agent-Plan task 3).

    Statuses: pending -> running -> succeeded | failed | cancelled. Terminal
    statuses are final for 'update_status', 'lease', 'set_plan' and
    'set_progress'; 'cancel' is the only unconditional override and wins
    even while the job is leased by someone else.
    """

    def create(self, job_id: str, spec_text: str) -> AgentJob:
        """Insert a pending job; 'spec_digest' is always sha256(spec_text).

        Raises JobAlreadyExistsError when 'job_id' is already taken.
        """
        ...

    def get(self, job_id: str) -> AgentJob | None:
        """Return the current projection, or None when unknown."""
        ...

    def list(
        self,
        *,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentJob]:
        """Return jobs ordered by 'created_at' then 'id'.

        'status' filters when given; limit >= 1 and offset >= 0 are
        enforced (ValueError otherwise).
        """
        ...

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        result_json: Mapping[str, Any] | None = None,
    ) -> AgentJob:
        """Transition 'job_id' to 'status' and return the new projection.

        Any non-terminal status may move to any other status (pending ->
        succeeded included). A terminal job accepts only its own status
        (idempotent no-op); any other target raises InvalidJobTransitionError —
        use cancel() for the deliberate override. Entering 'running' sets
        'started_at' once; entering a terminal status sets 'finished_at'
        once and releases any lease. 'error' and 'result_json'
        (JSON-serialized) are attached when provided. Raises
        JobNotFoundError for unknown ids and ValueError for an unknown
        status string.
        """
        ...

    def set_plan(self, job_id: str, plan: Mapping[str, Any]) -> AgentJob:
        """Replace 'plan_json' (JSON-serialized). Rejected on terminal jobs."""
        ...

    def set_progress(
        self,
        job_id: str,
        current_step: str,
        progress: Mapping[str, Any],
    ) -> AgentJob:
        """Set 'current_step' and replace 'progress_json'.

        Rejected on terminal jobs (InvalidJobTransitionError) — cancel wins
        over late projections.
        """
        ...

    def lease(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        """Atomically acquire the lease; True iff granted.

        Granted only for a non-terminal job whose lease is free, expired
        ('lease_expires_at <= now'), or already held by 'owner'. On grant:
        lease_owner = owner, lease_expires_at = now + ttl,
        pending -> running and 'started_at' is set once. Returns False on
        contention or for a terminal job; raises JobNotFoundError for
        unknown ids and ValueError for ttl_seconds <= 0.
        """
        ...

    def renew(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        """Extend 'lease_expires_at' to now + ttl.

        Succeeds only while 'owner' still holds the lease and the job is
        non-terminal; False otherwise (JobNotFoundError if unknown,
        ValueError for ttl_seconds <= 0).
        """
        ...

    def release(self, job_id: str, owner: str) -> bool:
        """Clear the lease iff 'owner' holds it; False otherwise.

        A terminal job no longer carries a lease, so release returns False
        for it as well. JobNotFoundError for unknown ids.
        """
        ...

    def cancel(self, job_id: str, reason: str) -> AgentJob:
        """Cancel unconditionally — wins even while the job is leased.

        Sets status 'cancelled', error = reason, clears the lease and sets
        'finished_at' once. As the documented override it also flips other
        terminal states (succeeded/failed) and is idempotent. Returns the
        updated projection; JobNotFoundError for unknown ids.
        """
        ...

    def ensure_schema(self) -> None:
        """Create the backing table (idempotent; SQLite also runs it at init)."""
        ...

    def close(self) -> None:
        """Release backend resources (no-op for in-memory / per-op MySQL)."""
        ...


# ── Shared portable SQL (the hub both SQL backends read) ─────────────────────

_SCHEMA_SQL: str = (
    "CREATE TABLE IF NOT EXISTS agent_jobs ("
    "id VARCHAR(255) PRIMARY KEY, "
    "status VARCHAR(16) NOT NULL, "
    "spec_text TEXT NOT NULL, "
    "spec_digest CHAR(64) NOT NULL, "
    "plan_json TEXT, "
    "current_step VARCHAR(255), "
    "progress_json TEXT, "
    "lease_owner VARCHAR(255), "
    "lease_expires_at DOUBLE, "
    "started_at DOUBLE, "
    "finished_at DOUBLE, "
    "result_json TEXT, "
    "error TEXT, "
    "created_at DOUBLE NOT NULL, "
    "updated_at DOUBLE NOT NULL)"
)

_INSERT_SQL: str = (
    "INSERT INTO agent_jobs "
    "(id, status, spec_text, spec_digest, created_at, updated_at) "
    "VALUES (?, 'pending', ?, ?, ?, ?)"
)

_SELECT_BY_ID_SQL: str = (
    "SELECT id, status, spec_text, spec_digest, plan_json, current_step, "
    "progress_json, lease_owner, lease_expires_at, started_at, finished_at, "
    "result_json, error, created_at, updated_at FROM agent_jobs WHERE id = ?"
)

_LIST_SQL: str = (
    "SELECT id, status, spec_text, spec_digest, plan_json, current_step, "
    "progress_json, lease_owner, lease_expires_at, started_at, finished_at, "
    "result_json, error, created_at, updated_at FROM agent_jobs "
    "ORDER BY created_at ASC, id ASC LIMIT ? OFFSET ?"
)

_LIST_BY_STATUS_SQL: str = (
    "SELECT id, status, spec_text, spec_digest, plan_json, current_step, "
    "progress_json, lease_owner, lease_expires_at, started_at, finished_at, "
    "result_json, error, created_at, updated_at FROM agent_jobs "
    "WHERE status = ? ORDER BY created_at ASC, id ASC LIMIT ? OFFSET ?"
)

_LEASE_SQL: str = (
    "UPDATE agent_jobs SET lease_owner = ?, lease_expires_at = ?, updated_at = ?, "
    "status = CASE WHEN status = 'pending' THEN 'running' ELSE status END, "
    "started_at = COALESCE(started_at, ?) "
    "WHERE id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled') "
    "AND (lease_owner IS NULL OR lease_owner = ? "
    "OR lease_expires_at IS NULL OR lease_expires_at <= ?)"
)

_RENEW_SQL: str = (
    "UPDATE agent_jobs SET lease_expires_at = ?, updated_at = ? "
    "WHERE id = ? AND lease_owner = ? "
    "AND status NOT IN ('succeeded', 'failed', 'cancelled')"
)

_RELEASE_SQL: str = (
    "UPDATE agent_jobs SET lease_owner = NULL, lease_expires_at = NULL, updated_at = ? "
    "WHERE id = ? AND lease_owner = ?"
)

_CANCEL_SQL: str = (
    "UPDATE agent_jobs SET status = 'cancelled', error = ?, lease_owner = NULL, "
    "lease_expires_at = NULL, finished_at = COALESCE(finished_at, ?), updated_at = ? "
    "WHERE id = ?"
)

_SET_PLAN_SQL: str = (
    "UPDATE agent_jobs SET plan_json = ?, updated_at = ? "
    "WHERE id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')"
)

_SET_PROGRESS_SQL: str = (
    "UPDATE agent_jobs SET current_step = ?, progress_json = ?, updated_at = ? "
    "WHERE id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')"
)

_UPDATE_STATUS_NONTERMINAL_SQL: str = (
    "UPDATE agent_jobs SET status = ?, error = COALESCE(?, error), "
    "result_json = COALESCE(?, result_json), updated_at = ?, "
    "started_at = COALESCE(started_at, ?) "
    "WHERE id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')"
)

_UPDATE_STATUS_TERMINAL_SQL: str = (
    "UPDATE agent_jobs SET status = ?, error = COALESCE(?, error), "
    "result_json = COALESCE(?, result_json), updated_at = ?, "
    "started_at = COALESCE(started_at, ?), "
    "finished_at = COALESCE(finished_at, ?), "
    "lease_owner = NULL, lease_expires_at = NULL "
    "WHERE id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')"
)


# ── Shared helpers ────────────────────────────────────────────────────────────


def _to_mysql(sql: str) -> str:
    """Translate the shared '?' placeholder SQL to PyMySQL's '%s'."""
    return sql.replace("?", "%s")


def _validate_status(status: str) -> JobStatus:
    if status not in _STATUS_VALUES:
        raise ValueError(f"unknown job status {status!r}; expected one of {JOB_STATUSES}")
    return cast(JobStatus, status)


def _validate_list_args(limit: int, offset: int) -> None:
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")


def _denied_or_missing(job: AgentJob | None, job_id: str) -> bool:
    if job is None:
        raise JobNotFoundError(f"agent job {job_id!r} not found")
    return False


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _row_to_job(row: Any) -> AgentJob:
    return AgentJob(
        id=cast(str, row["id"]),
        status=cast(JobStatus, row["status"]),
        spec_text=cast(str, row["spec_text"]),
        spec_digest=cast(str, row["spec_digest"]),
        plan_json=_opt_str(row["plan_json"]),
        current_step=_opt_str(row["current_step"]),
        progress_json=_opt_str(row["progress_json"]),
        lease_owner=_opt_str(row["lease_owner"]),
        lease_expires_at=_opt_float(row["lease_expires_at"]),
        started_at=_opt_float(row["started_at"]),
        finished_at=_opt_float(row["finished_at"]),
        result_json=_opt_str(row["result_json"]),
        error=_opt_str(row["error"]),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _update_status_sql(
    job_id: str,
    new_status: JobStatus,
    now: float,
    error: str | None,
    result_json: Mapping[str, Any] | None,
) -> tuple[str, tuple[Any, ...]]:
    """Bind parameters onto the fully static UPDATE statement for the target.

    COALESCE turns the optional error / result_json / started_at columns
    into no-ops when their parameter is None; every value travels through a
    placeholder, never through SQL text.
    """
    payload = json.dumps(dict(result_json)) if result_json is not None else None
    started_arg = now if new_status == "running" else None
    if new_status in TERMINAL_JOB_STATUSES:
        return _UPDATE_STATUS_TERMINAL_SQL, (
            new_status,
            error,
            payload,
            now,
            started_arg,
            now,
            job_id,
        )
    return _UPDATE_STATUS_NONTERMINAL_SQL, (
        new_status,
        error,
        payload,
        now,
        started_arg,
        job_id,
    )


def _transition_result(
    store: AgentJobStore, job_id: str, new_status: JobStatus, affected: int
) -> AgentJob:
    if affected == 0:
        current = store.get(job_id)
        if current is None:
            raise JobNotFoundError(f"agent job {job_id!r} not found")
        if current.status == new_status:
            return current
        raise InvalidJobTransitionError(
            f"cannot move terminal job {job_id!r} from {current.status!r} "
            f"to {new_status!r}; use cancel() to override"
        )
    job = store.get(job_id)
    if job is None:
        raise JobNotFoundError(f"agent job {job_id!r} not found")
    return job


def _projection_after_write(store: AgentJobStore, job_id: str, affected: int) -> AgentJob:
    if affected == 0:
        current = store.get(job_id)
        if current is None:
            raise JobNotFoundError(f"agent job {job_id!r} not found")
        raise InvalidJobTransitionError(
            f"job {job_id!r} is terminal ({current.status}); projections are closed"
        )
    job = store.get(job_id)
    if job is None:
        raise JobNotFoundError(f"agent job {job_id!r} not found")
    return job


# ── In-memory backend ─────────────────────────────────────────────────────────


class InMemoryAgentJobStore:
    """Thread-safe in-memory backend — development and tests."""

    def __init__(self, *, now_fn: Callable[[], float] | None = None) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.RLock()
        self._jobs: dict[str, AgentJob] = {}

    def ensure_schema(self) -> None:
        """No-op: the in-memory dict needs no schema."""

    def close(self) -> None:
        """No-op: nothing to release."""

    def create(self, job_id: str, spec_text: str) -> AgentJob:
        now = self._now_fn()
        job = AgentJob(
            id=job_id,
            status="pending",
            spec_text=spec_text,
            spec_digest=compute_spec_digest(spec_text),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            if job_id in self._jobs:
                raise JobAlreadyExistsError(f"agent job {job_id!r} already exists")
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> AgentJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(
        self,
        *,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentJob]:
        _validate_list_args(limit, offset)
        with self._lock:
            matching = [
                job for job in self._jobs.values() if status is None or job.status == status
            ]
            matching.sort(key=lambda job: (job.created_at, job.id))
            return matching[offset : offset + limit]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        result_json: Mapping[str, Any] | None = None,
    ) -> AgentJob:
        new_status = _validate_status(status)
        now = self._now_fn()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"agent job {job_id!r} not found")
            if job.status in TERMINAL_JOB_STATUSES:
                if job.status == new_status:
                    return job
                raise InvalidJobTransitionError(
                    f"cannot move terminal job {job_id!r} from {job.status!r} "
                    f"to {new_status!r}; use cancel() to override"
                )
            changes: dict[str, Any] = {"status": new_status, "updated_at": now}
            if error is not None:
                changes["error"] = error
            if result_json is not None:
                changes["result_json"] = json.dumps(dict(result_json))
            if new_status == "running" and job.started_at is None:
                changes["started_at"] = now
            if new_status in TERMINAL_JOB_STATUSES:
                if job.finished_at is None:
                    changes["finished_at"] = now
                changes["lease_owner"] = None
                changes["lease_expires_at"] = None
            updated = replace(job, **changes)
            self._jobs[job_id] = updated
            return updated

    def set_plan(self, job_id: str, plan: Mapping[str, Any]) -> AgentJob:
        now = self._now_fn()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"agent job {job_id!r} not found")
            if job.status in TERMINAL_JOB_STATUSES:
                raise InvalidJobTransitionError(
                    f"job {job_id!r} is terminal ({job.status}); projections are closed"
                )
            updated = replace(job, plan_json=json.dumps(dict(plan)), updated_at=now)
            self._jobs[job_id] = updated
            return updated

    def set_progress(
        self,
        job_id: str,
        current_step: str,
        progress: Mapping[str, Any],
    ) -> AgentJob:
        now = self._now_fn()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"agent job {job_id!r} not found")
            if job.status in TERMINAL_JOB_STATUSES:
                raise InvalidJobTransitionError(
                    f"job {job_id!r} is terminal ({job.status}); projections are closed"
                )
            updated = replace(
                job,
                current_step=current_step,
                progress_json=json.dumps(dict(progress)),
                updated_at=now,
            )
            self._jobs[job_id] = updated
            return updated

    def lease(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        now = self._now_fn()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"agent job {job_id!r} not found")
            if job.status in TERMINAL_JOB_STATUSES:
                return False
            held_by_other = job.lease_owner is not None and job.lease_owner != owner
            unexpired = job.lease_expires_at is not None and job.lease_expires_at > now
            if held_by_other and unexpired:
                return False
            changes: dict[str, Any] = {
                "lease_owner": owner,
                "lease_expires_at": now + ttl_seconds,
                "updated_at": now,
            }
            if job.status == "pending":
                changes["status"] = "running"
            if job.started_at is None:
                changes["started_at"] = now
            self._jobs[job_id] = replace(job, **changes)
            return True

    def renew(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        now = self._now_fn()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"agent job {job_id!r} not found")
            if job.status in TERMINAL_JOB_STATUSES or job.lease_owner != owner:
                return False
            updated = replace(
                job, lease_expires_at=now + ttl_seconds, updated_at=now
            )
            self._jobs[job_id] = updated
            return True

    def release(self, job_id: str, owner: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"agent job {job_id!r} not found")
            if job.lease_owner != owner:
                return False
            updated = replace(
                job,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=self._now_fn(),
            )
            self._jobs[job_id] = updated
            return True

    def cancel(self, job_id: str, reason: str) -> AgentJob:
        now = self._now_fn()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(f"agent job {job_id!r} not found")
            changes: dict[str, Any] = {
                "status": "cancelled",
                "error": reason,
                "lease_owner": None,
                "lease_expires_at": None,
                "updated_at": now,
            }
            if job.finished_at is None:
                changes["finished_at"] = now
            updated = replace(job, **changes)
            self._jobs[job_id] = updated
            return updated


# ── SQLite backend ────────────────────────────────────────────────────────────


class SqliteAgentJobStore:
    """File-based SQLite backend (dev fallback; unit tests run it, no Docker).

    One connection per store instance, serialized by a lock;
    check_same_thread=False plus the lock keeps concurrent threads safe.
    The schema is created in __init__.
    """

    def __init__(
        self, path: str | Path, *, now_fn: Callable[[], float] | None = None
    ) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(_SCHEMA_SQL)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create(self, job_id: str, spec_text: str) -> AgentJob:
        now = self._now_fn()
        digest = compute_spec_digest(spec_text)
        with self._lock, self._conn:
            try:
                self._conn.execute(_INSERT_SQL, (job_id, spec_text, digest, now, now))
            except sqlite3.IntegrityError as exc:
                raise JobAlreadyExistsError(
                    f"agent job {job_id!r} already exists"
                ) from exc
        return AgentJob(
            id=job_id,
            status="pending",
            spec_text=spec_text,
            spec_digest=compute_spec_digest(spec_text),
            created_at=now,
            updated_at=now,
        )

    def get(self, job_id: str) -> AgentJob | None:
        with self._lock:
            row = self._conn.execute(_SELECT_BY_ID_SQL, (job_id,)).fetchone()
        return None if row is None else _row_to_job(row)

    def list(
        self,
        *,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentJob]:
        _validate_list_args(limit, offset)
        if status is not None:
            sql = _LIST_BY_STATUS_SQL
            params: tuple[Any, ...] = (status, limit, offset)
        else:
            sql = _LIST_SQL
            params = (limit, offset)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_job(row) for row in rows]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        result_json: Mapping[str, Any] | None = None,
    ) -> AgentJob:
        new_status = _validate_status(status)
        now = self._now_fn()
        sql, params = _update_status_sql(job_id, new_status, now, error, result_json)
        with self._lock, self._conn:
            affected = self._conn.execute(sql, params).rowcount
        return _transition_result(self, job_id, new_status, affected)

    def set_plan(self, job_id: str, plan: Mapping[str, Any]) -> AgentJob:
        now = self._now_fn()
        with self._lock, self._conn:
            affected = self._conn.execute(
                _SET_PLAN_SQL, (json.dumps(dict(plan)), now, job_id)
            ).rowcount
        return _projection_after_write(self, job_id, affected)

    def set_progress(
        self,
        job_id: str,
        current_step: str,
        progress: Mapping[str, Any],
    ) -> AgentJob:
        now = self._now_fn()
        with self._lock, self._conn:
            affected = self._conn.execute(
                _SET_PROGRESS_SQL,
                (current_step, json.dumps(dict(progress)), now, job_id),
            ).rowcount
        return _projection_after_write(self, job_id, affected)

    def lease(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        now = self._now_fn()
        expires_at = now + ttl_seconds
        with self._lock, self._conn:
            affected = self._conn.execute(
                _LEASE_SQL, (owner, expires_at, now, now, job_id, owner, now)
            ).rowcount
        if affected == 1:
            return True
        return _denied_or_missing(self.get(job_id), job_id)

    def renew(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        now = self._now_fn()
        with self._lock, self._conn:
            affected = self._conn.execute(
                _RENEW_SQL, (now + ttl_seconds, now, job_id, owner)
            ).rowcount
        if affected == 1:
            return True
        return _denied_or_missing(self.get(job_id), job_id)

    def release(self, job_id: str, owner: str) -> bool:
        now = self._now_fn()
        with self._lock, self._conn:
            affected = self._conn.execute(
                _RELEASE_SQL, (now, job_id, owner)
            ).rowcount
        if affected == 1:
            return True
        return _denied_or_missing(self.get(job_id), job_id)

    def cancel(self, job_id: str, reason: str) -> AgentJob:
        now = self._now_fn()
        with self._lock, self._conn:
            affected = self._conn.execute(
                _CANCEL_SQL, (reason, now, now, job_id)
            ).rowcount
        if affected == 0:
            raise JobNotFoundError(f"agent job {job_id!r} not found")
        job = self.get(job_id)
        if job is None:
            raise JobNotFoundError(f"agent job {job_id!r} not found")
        return job


# ── MySQL backend ─────────────────────────────────────────────────────────────


def _parse_mysql_url(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError(f"expected a mysql:// URL, got scheme {parsed.scheme!r}")
    if parsed.hostname is None:
        raise ValueError("MySQL URL must include a host")
    database = (parsed.path or "/").lstrip("/")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username is not None else "",
        "password": unquote(parsed.password) if parsed.password is not None else "",
        "database": database or "specproof",
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


class MySqlAgentJobStore:
    """Production MySQL backend (PyMySQL + DictCursor).

    One connection per operation via the connection() context manager,
    which commits on success and rolls back on error; every statement uses
    a single cursor execute-then-fetch (CLAUDE.md MySQL discipline). Call
    ensure_schema() explicitly before first use — the shared DDL carries no
    MySQL-only syntax.
    """

    def __init__(
        self, url: str | None = None, *, now_fn: Callable[[], float] | None = None
    ) -> None:
        resolved = url or os.getenv("MYSQL_URL")
        if not resolved:
            raise ValueError(
                "MySqlAgentJobStore needs a mysql:// URL (argument or MYSQL_URL)"
            )
        self._connect_kwargs = _parse_mysql_url(resolved)
        self._now_fn = now_fn if now_fn is not None else time.time

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(**self._connect_kwargs)

    @contextmanager
    def connection(self) -> Iterator[pymysql.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        """No-op: each operation opens and closes its own connection."""

    def ensure_schema(self) -> None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_SCHEMA_SQL)

    def create(self, job_id: str, spec_text: str) -> AgentJob:
        now = self._now_fn()
        digest = compute_spec_digest(spec_text)
        with self.connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    _to_mysql(_INSERT_SQL), (job_id, spec_text, digest, now, now)
                )
            except pymysql.err.IntegrityError as exc:
                raise JobAlreadyExistsError(
                    f"agent job {job_id!r} already exists"
                ) from exc
        return AgentJob(
            id=job_id,
            status="pending",
            spec_text=spec_text,
            spec_digest=digest,
            created_at=now,
            updated_at=now,
        )

    def get(self, job_id: str) -> AgentJob | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_BY_ID_SQL), (job_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_job(cast(dict[str, Any], row))

    def list(
        self,
        *,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentJob]:
        _validate_list_args(limit, offset)
        if status is not None:
            sql = _LIST_BY_STATUS_SQL
            params: tuple[Any, ...] = (status, limit, offset)
        else:
            sql = _LIST_SQL
            params = (limit, offset)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(sql), params)
            rows = cur.fetchall()
        return [_row_to_job(row) for row in rows]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        result_json: Mapping[str, Any] | None = None,
    ) -> AgentJob:
        new_status = _validate_status(status)
        now = self._now_fn()
        sql, params = _update_status_sql(job_id, new_status, now, error, result_json)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(sql), params)
            affected = cur.rowcount
        return _transition_result(self, job_id, new_status, affected)

    def set_plan(self, job_id: str, plan: Mapping[str, Any]) -> AgentJob:
        now = self._now_fn()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                _to_mysql(_SET_PLAN_SQL), (json.dumps(dict(plan)), now, job_id)
            )
            affected = cur.rowcount
        return _projection_after_write(self, job_id, affected)

    def set_progress(
        self,
        job_id: str,
        current_step: str,
        progress: Mapping[str, Any],
    ) -> AgentJob:
        now = self._now_fn()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                _to_mysql(_SET_PROGRESS_SQL),
                (current_step, json.dumps(dict(progress)), now, job_id),
            )
            affected = cur.rowcount
        return _projection_after_write(self, job_id, affected)

    def lease(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        now = self._now_fn()
        expires_at = now + ttl_seconds
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                _to_mysql(_LEASE_SQL),
                (owner, expires_at, now, now, job_id, owner, now),
            )
            affected = cur.rowcount
        if affected == 1:
            return True
        return _denied_or_missing(self.get(job_id), job_id)

    def renew(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        now = self._now_fn()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                _to_mysql(_RENEW_SQL), (now + ttl_seconds, now, job_id, owner)
            )
            affected = cur.rowcount
        if affected == 1:
            return True
        return _denied_or_missing(self.get(job_id), job_id)

    def release(self, job_id: str, owner: str) -> bool:
        now = self._now_fn()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_RELEASE_SQL), (now, job_id, owner))
            affected = cur.rowcount
        if affected == 1:
            return True
        return _denied_or_missing(self.get(job_id), job_id)

    def cancel(self, job_id: str, reason: str) -> AgentJob:
        now = self._now_fn()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_CANCEL_SQL), (reason, now, now, job_id))
            affected = cur.rowcount
        if affected == 0:
            raise JobNotFoundError(f"agent job {job_id!r} not found")
        job = self.get(job_id)
        if job is None:
            raise JobNotFoundError(f"agent job {job_id!r} not found")
        return job


# ──────────────────────────────────────────────────────────────────────────────
# Integration note (Agent-Plan task 3) — where CraftLoop would wire this store.
# craft/loop.py is owned by another lane and was intentionally NOT modified.
#
# 1. Job intake — in CraftLoop.__init__, right after
#    "self.job_id = job_id or default_job_id()" (craft/loop.py ~line 240),
#    or at the top of CraftLoop.run():
#        store.create(self.job_id, json.dumps(self.spec.to_dict()))
#    (resume paths should probe with store.get(self.job_id) instead of
#    re-creating, since create raises JobAlreadyExistsError).
#
# 2. Lease / guard — at the top of CraftLoop.run(), before the step loop:
#        owner = f"{socket.gethostname()}:{os.getpid()}:{self.job_id}"
#        if not store.lease(self.job_id, owner, ttl_seconds=...):
#            raise CraftLoopError("job is leased by another worker or finished")
#    Inside the step loop, renew per step and watch for cancellation:
#        if store.get(self.job_id).status == "cancelled":
#            ... flush an honest 'cancelled' checkpoint entry and return ...
#        store.renew(self.job_id, owner, ttl_seconds=...)
#
# 3. Projection — once after planning, and after every self._checkpoint(...)
#    call in run() (craft/loop.py ~lines 340-501):
#        store.set_plan(self.job_id, plan_payload)            # plan serialization
#        store.set_progress(self.job_id, current_step=state.step.id,
#                           progress={"status": state.status,
#                                     "iterations": state.iterations,
#                                     "evidence": state.evidence})
#
# 4. Terminal write — in _finish(result) (craft/loop.py ~line 834), before or
#    right after writing report.json:
#        mapped = "succeeded" if result == "DONE" else "failed"
#        store.update_status(self.job_id, mapped, result_json=report)
#    Entering a terminal status releases the lease automatically, so no
#    explicit release() call is needed on the happy path.
#
# 5. Cancellation — a supervisor (API / CLI) calls without holding the lease:
#        store.cancel(job_id, reason)
#    cancel wins even while leased; the running CraftLoop notices via the
#    step-loop get() check in (2) and exits without racing a conflicting
#    terminal status (update_status on a cancelled job raises
#    InvalidJobTransitionError).
#
# 6. Recovery — CraftLoop.from_checkpoint rebuilds the in-memory loop; re-run
#    (2) to re-acquire the lease and resume after the last green step.
# ──────────────────────────────────────────────────────────────────────────────
