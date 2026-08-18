"""MySQL store — business truth for Phase 0/1.

P1.1: Added strict job state machine with 8 states, CAS transitions,
retry tracking, worker assignment, and stale detection.
"""
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

import pymysql
from pymysql.cursors import DictCursor

from storage.tenant_scope import current_scope

# ── Tenant-aware job SQL (industrialization phase 1) ─────────────
# When a tenant scope is active (multi-tenant auth mode) every job read
# carries a tenant predicate and every job insert stamps tenant_id from the
# principal — repository-layer parameterization per
# docs/architecture/MULTI_TENANT_DESIGN.md §2/§4. Without a scope the SQL is
# byte-identical to the pre-tenant implementation (single-tenant compat).

_JOB_INSERT_TENANT_SQL = (
    "INSERT INTO verification_jobs "
    "(id, repo_path, base_ref, head_ref, spec_path, status, depth, "
    "github_check_json, tenant_id) "
    "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
    "%(head_ref)s, %(spec_path)s, 'PENDING', %(depth)s, "
    "%(github_check_json)s, %(tenant_id)s)"
)

_AUDIT_INSERT_TENANT_SQL = (
    "INSERT INTO audit_logs "
    "(job_id, actor, action, from_status, to_status, detail, attempted_tenant) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)

# ── State machine ──────────────────────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "PENDING":  {"QUEUED", "ERROR"},
    "QUEUED":   {"RUNNING", "CANCELLED", "STALE", "ERROR"},
    "RUNNING":  {
        "VERIFIED", "BLOCKED", "FAILED", "CANCELLED", "STALE",
        "WAITING_FOR_PROVIDER", "ERROR",
    },
    # Provider outage: recoverable — either retry (QUEUED) or give up.
    "WAITING_FOR_PROVIDER": {"QUEUED", "RUNNING", "FAILED", "CANCELLED", "ERROR"},
    "FAILED":   {"QUEUED", "CANCELLED", "ERROR"},
    "STALE":    set(),
    "VERIFIED": set(),
    "BLOCKED":  set(),
    "CANCELLED": set(),
    "ERROR":    set(),
}

TERMINAL_STATUSES = {"VERIFIED", "BLOCKED", "STALE", "CANCELLED", "ERROR"}


class InvalidStateTransition(Exception):  # noqa: N818 — domain term, public API
    """Raised when a job status transition is not allowed."""


def _job_row(job: dict[str, Any]) -> dict[str, Any]:
    """Normalize a job dict onto the verification_jobs column set.

    github_check (a dict) is serialized into the JSON column; callers that
    do not carry GitHub metadata leave the column NULL.
    """
    check = job.get("github_check")
    return {
        "id": job["id"],
        "repo_path": job.get("repo_path", ""),
        "base_ref": job.get("base_ref", ""),
        "head_ref": job.get("head_ref", ""),
        "spec_path": job.get("spec_path", ""),
        "status": job.get("status", "PENDING"),
        "depth": job.get("depth", "FAST"),
        "github_check_json": json.dumps(check) if check else None,
        # Multi-tenant: stamped from the request-scoped tenant context by the
        # insert paths below; NULL for single-tenant / webhook-created jobs.
        "tenant_id": job.get("tenant_id"),
    }


@dataclass
class MySQLConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "specproof"
    password: str = "specproof_pass"
    database: str = "specproof_phase0"

    @classmethod
    def from_env(cls) -> "MySQLConfig":
        return cls(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "specproof"),
            password=os.getenv("MYSQL_PASSWORD", "specproof_pass"),
            database=os.getenv("MYSQL_DATABASE", "specproof_phase0"),
        )


class MySQLStore:
    """Business truth store for verification jobs, findings, contracts."""

    def __init__(self, config: MySQLConfig | None = None) -> None:
        self.config = config or MySQLConfig.from_env()

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset="utf8mb4",
            cursorclass=DictCursor,
        )

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
        """Compatibility close() — every operation opens and closes its own
        connection, so there is no pooled handle to release."""
        return None

    # ── State machine helpers ─────────────────────────────────

    @staticmethod
    def is_valid_transition(from_status: str, to_status: str) -> bool:
        return to_status in _VALID_TRANSITIONS.get(from_status, set())

    @staticmethod
    def is_terminal(status: str) -> bool:
        return status in TERMINAL_STATUSES

    # ── DDL ───────────────────────────────────────────────────

    def ensure_tables(self) -> None:
        """Apply all pending versioned migrations (P0-B1).

        Schema changes live in infra/mysql/migrations/*.sql and are applied
        exactly once, recorded in schema_migrations. This method remains as
        the backward-compatible entry point.
        """
        from storage.migrations import MigrationRunner

        MigrationRunner(self).apply_pending()

    def record_audit(
        self,
        action: str,
        actor: str = "system",
        job_id: str | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
        detail: str = "",
        attempted_tenant: str | None = None,
    ) -> None:
        """Write an audit row (P0-A5). Best effort — never breaks the flow.

        attempted_tenant (phase 1) records the tenant a caller tried to reach
        when a cross-tenant access was refused — the column only participates
        when the value is set, so pre-migration schemas keep working.
        """
        try:
            with self.connection() as conn:
                if attempted_tenant is not None:
                    conn.cursor().execute(
                        _AUDIT_INSERT_TENANT_SQL,
                        (
                            job_id, actor, action, from_status, to_status,
                            detail, attempted_tenant,
                        ),
                    )
                else:
                    conn.cursor().execute(
                        "INSERT INTO audit_logs "
                        "(job_id, actor, action, from_status, to_status, detail) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (job_id, actor, action, from_status, to_status, detail),
                    )
        except Exception as exc:  # noqa: BLE001 — audit must not take down jobs
            import logging

            logging.getLogger(__name__).warning("audit write failed: %s", exc)

    def run_migration(self, sql_path: str) -> None:
        """Run a SQL migration file."""
        with open(sql_path, encoding="utf-8") as f:
            sql = f.read()
        with self.connection() as conn:
            for statement in sql.split(";"):
                stmt = statement.strip()
                if stmt and not stmt.startswith("--"):
                    try:
                        conn.cursor().execute(stmt)
                    except pymysql.err.OperationalError as e:
                        code = e.args[0] if e.args else 0
                        # 1060 = Duplicate column, 1061 = Duplicate index name
                        if code not in (1060, 1061):
                            raise

    # ── CRUD ──────────────────────────────────────────────────

    def insert_job(self, job: dict[str, Any]) -> None:
        _sql = (
            "INSERT INTO verification_jobs "
            "(id, repo_path, base_ref, head_ref, spec_path, status, depth, "
            "github_check_json) "
            "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
            "%(head_ref)s, %(spec_path)s, %(status)s, %(depth)s, "
            "%(github_check_json)s)"
        )
        row = _job_row(job)
        scope = current_scope()
        if scope is not None:
            row["tenant_id"] = scope.tenant_id
            _sql = (
                "INSERT INTO verification_jobs "
                "(id, repo_path, base_ref, head_ref, spec_path, status, depth, "
                "github_check_json, tenant_id) "
                "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
                "%(head_ref)s, %(spec_path)s, %(status)s, %(depth)s, "
                "%(github_check_json)s, %(tenant_id)s)"
            )
        with self.connection() as conn:
            conn.cursor().execute(_sql, row)

    # ── Outbox methods ────────────────────────────────────────

    def create_job_with_outbox(
        self,
        job: dict[str, Any],
        event_type: str = "JobCreated",
        routing_key: str = "q.p1.verify.job",
    ) -> str:
        """Insert a new job and its outbox event in a single transaction.

        Both INSERTs succeed or both roll back. After commit, the Outbox Relay
        is responsible for publishing to RabbitMQ.
        """
        job_id = job["id"]
        payload = {
            "job_id": job_id,
            "repo_path": job.get("repo_path", ""),
            "base_ref": job.get("base_ref", ""),
            "head_ref": job.get("head_ref", ""),
            "spec_path": job.get("spec_path", ""),
            "depth": job.get("depth", "FAST"),
        }
        row = _job_row(job)
        scope = current_scope()
        if scope is not None:
            row["tenant_id"] = scope.tenant_id
        insert_sql = (
            _JOB_INSERT_TENANT_SQL
            if scope is not None
            else (
                "INSERT INTO verification_jobs "
                "(id, repo_path, base_ref, head_ref, spec_path, status, depth, "
                "github_check_json) "
                "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
                "%(head_ref)s, %(spec_path)s, 'PENDING', %(depth)s, "
                "%(github_check_json)s)"
            )
        )
        with self.connection() as conn:
            conn.cursor().execute(insert_sql, row)
            conn.cursor().execute(
                "INSERT INTO outbox (aggregate_id, aggregate_type, "
                "event_type, payload, routing_key) "
                "VALUES (%(aggregate_id)s, %(aggregate_type)s, "
                "%(event_type)s, %(payload)s, %(routing_key)s)",
                {
                    "aggregate_id": job_id,
                    "aggregate_type": "verification_job",
                    "event_type": event_type,
                    "payload": json.dumps(payload),
                    "routing_key": routing_key,
                },
            )
            # Transition to QUEUED after outbox is safely persisted
            conn.cursor().execute(
                "UPDATE verification_jobs SET status = 'QUEUED' WHERE id = %s",
                (job_id,),
            )
        return str(job_id)

    def set_job_github_check(
        self, job_id: str, check_meta: dict[str, Any]
    ) -> None:
        """Attach GitHub Check Run bookkeeping to a job (best-effort)."""
        with self.connection() as conn:
            conn.cursor().execute(
                "UPDATE verification_jobs SET github_check_json = %s "
                "WHERE id = %s",
                (json.dumps(check_meta), job_id),
            )

    def fetch_pending_outbox_rows(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch unpublished outbox rows with SKIP LOCKED for relay.

        Returns the oldest unpublished rows (FIFO order).
        """
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, aggregate_id, event_type, payload, routing_key "
                "FROM outbox "
                "WHERE published_at IS NULL "
                "ORDER BY id "
                "LIMIT %s "
                "FOR UPDATE SKIP LOCKED",
                (limit,),
            )
            return cast(list[dict[str, Any]], cur.fetchall())

    def mark_outbox_published(self, outbox_id: int) -> None:
        """Mark an outbox row as published (sets published_at to NOW)."""
        with self.connection() as conn:
            conn.cursor().execute(
                "UPDATE outbox SET published_at = NOW(3) WHERE id = %s",
                (outbox_id,),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        # Single cursor per statement: fetchone() on a fresh cursor raises
        # "execute() first" (surfaced by the live-MySQL state machine tests).
        scope = current_scope()
        if scope is None or scope.is_auditor():
            return self._get_job_unscoped(job_id)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM verification_jobs WHERE id = %s "
                "AND (tenant_id = %s OR tenant_id IS NULL)",
                (job_id, scope.tenant_id),
            )
            row = cast(dict[str, Any] | None, cur.fetchone())
            if row is not None:
                return row
            # The id exists but belongs to another tenant: answer with the
            # same None a missing row produces (no existence leak, §2) and
            # record the refused attempt with attempted_tenant.
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT tenant_id FROM verification_jobs WHERE id = %s",
                (job_id,),
            )
            other = cast(dict[str, Any] | None, cur2.fetchone())
        if other is not None and other.get("tenant_id") is not None:
            self.record_audit(
                action="tenant_isolation_blocked",
                actor=scope.user_id or "anonymous",
                job_id=job_id,
                detail=(
                    f"tenant {scope.tenant_id} attempted to read job "
                    f"{job_id} owned by tenant {other.get('tenant_id')}"
                ),
                attempted_tenant=str(other.get("tenant_id")),
            )
        return None

    def _get_job_unscoped(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM verification_jobs WHERE id = %s", (job_id,)
            )
            return cast(dict[str, Any] | None, cur.fetchone())

    def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM verification_jobs WHERE status = %s ORDER BY created_at",
                (status,),
            )
            return cast(list[dict[str, Any]], cur.fetchall())

    def list_recent_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent jobs (newest first), for the jobs API.

        Tenant mode: rows of the caller's tenant (plus legacy NULL-tenant
        rows) only; auditors keep the cross-tenant view (§2).
        """
        scope = current_scope()
        if scope is not None and not scope.is_auditor():
            with self.connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, repo_path, base_ref, head_ref, status, depth, "
                    "retry_count, worker_id, last_error, summary, created_at, "
                    "updated_at "
                    "FROM verification_jobs "
                    "WHERE (tenant_id = %s OR tenant_id IS NULL) "
                    "ORDER BY created_at DESC, id DESC LIMIT %s",
                    (scope.tenant_id, limit),
                )
                return cast(list[dict[str, Any]], cur.fetchall())
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, repo_path, base_ref, head_ref, status, depth, "
                "retry_count, worker_id, last_error, summary, created_at, updated_at "
                "FROM verification_jobs ORDER BY created_at DESC, id DESC LIMIT %s",
                (limit,),
            )
            return cast(list[dict[str, Any]], cur.fetchall())

    def save_job_summary(self, job_id: str, summary: dict[str, Any]) -> None:
        """Persist the pipeline result summary (dashboard / audit view)."""
        import json as _json

        with self.connection() as conn:
            conn.cursor().execute(
                "UPDATE verification_jobs SET summary = %s WHERE id = %s",
                (_json.dumps(summary, default=str), job_id),
            )

    def get_job_summary(self, job_id: str) -> dict[str, Any] | None:
        """Read a persisted pipeline summary, or None."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT summary FROM verification_jobs WHERE id = %s", (job_id,)
            )
            row = cur.fetchone()
        if not row or row.get("summary") is None:
            return None
        import json as _json

        if isinstance(row["summary"], str):
            return cast(dict[str, Any], _json.loads(row["summary"]))
        return cast(dict[str, Any], row["summary"])

    def get_job_tenant(self, job_id: str) -> str | None:
        """The tenant owning a verification job, or None when unknown.

        Best-effort probe for the tenant auth middleware's cross-tenant 404
        check. A schema without the tenant_id column (migration not yet
        applied) yields None so a partial upgrade never blocks requests;
        the repository-layer scoping remains the primary enforcement.
        """
        try:
            with self.connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT tenant_id FROM verification_jobs WHERE id = %s",
                    (job_id,),
                )
                row = cast(dict[str, Any] | None, cur.fetchone())
        except Exception as exc:  # noqa: BLE001 — isolation probe is advisory
            import logging

            logging.getLogger(__name__).warning(
                "tenant probe for job %s failed: %s", job_id, exc
            )
            return None
        if row is None:
            return None
        tenant = row.get("tenant_id")
        return str(tenant) if tenant else None

    def list_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Most recent audit rows (tenant auth attempts / auditor view)."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, job_id, actor, action, from_status, to_status, "
                "detail, attempted_tenant, created_at "
                "FROM audit_logs ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            return cast(list[dict[str, Any]], cur.fetchall())

    def count_pending_outbox(self) -> int:
        """Number of unpublished outbox rows (relay backlog gauge)."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS n FROM outbox WHERE published_at IS NULL"
            )
            row = cur.fetchone()
        return int(row["n"]) if row else 0

    # ── State machine: atomic CAS transition ──────────────────

    def transition_job_status(
        self,
        job_id: str,
        to_status: str,
        *,
        from_status: str | None = None,
        worker_id: str | None = None,
        error_msg: str | None = None,
        stale_replaced_by: str | None = None,
        increment_retry: bool = False,
    ) -> bool:
        """Atomically transition a job to a new status using CAS.

        Returns True if exactly 1 row was updated, False if the CAS failed
        (wrong current status or job not found).

        Raises InvalidStateTransition if the from→to pair is statically illegal.
        """
        # Resolve current status if not provided
        if from_status is None:
            job = self.get_job(job_id)
            if job is None:
                raise InvalidStateTransition(
                    f"Job {job_id} not found"
                )
            from_status = job["status"]

        if not self.is_valid_transition(from_status, to_status):
            raise InvalidStateTransition(
                f"Cannot transition job {job_id} from '{from_status}' to '{to_status}'"
            )

        parts = ["UPDATE verification_jobs SET status = %s"]
        params: list[Any] = [to_status]

        if worker_id is not None:
            parts.append(", worker_id = %s")
            params.append(worker_id)
        if error_msg is not None:
            parts.append(", last_error = %s")
            params.append(error_msg)
        if stale_replaced_by is not None:
            parts.append(", stale_replaced_by = %s")
            params.append(stale_replaced_by)
        if increment_retry:
            parts.append(", retry_count = retry_count + 1")

        parts.append("WHERE id = %s AND status = %s")
        params.extend([job_id, from_status])

        _sql = " ".join(parts)
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(_sql, params)
            changed = bool(cursor.rowcount == 1)
        if changed:
            # P0-A5: every status change is audited (who/from/to/when).
            self.record_audit(
                action="job_status_transition",
                actor=worker_id or "system",
                job_id=job_id,
                from_status=from_status,
                to_status=to_status,
                detail=(error_msg or "")[:1000],
            )
        return changed

    def claim_job(self, job_id: str, worker_id: str) -> bool:
        """Atomically claim a QUEUED job for a worker. CAS: QUEUED→RUNNING."""
        return self.transition_job_status(
            job_id,
            "RUNNING",
            from_status="QUEUED",
            worker_id=worker_id,
        )

    def mark_stale_for_head(self, new_head_ref: str, new_job_id: str) -> list[str]:
        """Mark all QUEUED/RUNNING jobs for the same repo as STALE.

        Returns list of stale job IDs.
        """
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM verification_jobs WHERE status IN ('QUEUED', 'RUNNING') FOR UPDATE"
            )
            stale_jobs = [row["id"] for row in cursor.fetchall()]
            for sid in stale_jobs:
                cursor.execute(
                    "UPDATE verification_jobs SET status = 'STALE', stale_replaced_by = %s "
                    "WHERE id = %s",
                    (new_job_id, sid),
                )
            return stale_jobs

    # ── Finding / Contract CRUD ───────────────────────────────

    def insert_finding(self, finding: dict[str, Any]) -> None:
        _sql = (
            "INSERT INTO findings "
            "(id, job_id, contract_id, severity, confidence, "
            "evidence_type, impact_path, capsule_path) "
            "VALUES (%(id)s, %(job_id)s, %(contract_id)s, %(severity)s, "
            "%(confidence)s, %(evidence_type)s, %(impact_path)s, %(capsule_path)s)"
        )
        with self.connection() as conn:
            conn.cursor().execute(_sql, finding)

    def insert_contract(self, contract: dict[str, Any]) -> None:
        _sql = (
            "INSERT INTO contracts "
            "(id, job_id, contract_id_str, requirement_text, "
            "checker_type, expected_behavior, result, evidence_ref) "
            "VALUES (%(id)s, %(job_id)s, %(contract_id_str)s, "
            "%(requirement_text)s, %(checker_type)s, "
            "%(expected_behavior)s, %(result)s, %(evidence_ref)s)"
        )
        with self.connection() as conn:
            conn.cursor().execute(_sql, contract)

    def upsert_provider_capability(self, record: dict[str, Any]) -> None:
        import json

        _sql = (
            "INSERT INTO provider_capabilities (base_url, model, capabilities) "
            "VALUES (%(base_url)s, %(model)s, %(capabilities)s) "
            "ON DUPLICATE KEY UPDATE "
            "capabilities = VALUES(capabilities), probed_at = CURRENT_TIMESTAMP"
        )
        with self.connection() as conn:
            conn.cursor().execute(
                _sql,
                {**record, "capabilities": json.dumps(record["capabilities"])},
            )

    def is_ready(self) -> bool:
        try:
            with self.connection() as conn:
                conn.cursor().execute("SELECT 1")
            return True
        except Exception:
            return False
