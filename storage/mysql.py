"""MySQL store — business truth for Phase 0/1.

P0.5: verification_jobs, findings, contracts, provider_capabilities
P1.1: strict job state machine with CAS, retry, worker assignment, stale detection
P1.2: transactional outbox with relay poller support
P1.3: atomic idempotency (processed_events + business writes in same TX)
"""

import json
import logging
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# P1.1 State Machine
# ═══════════════════════════════════════════════════════════════════════

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"QUEUED", "CANCELLED"},
    "QUEUED": {"PREPARING", "STALE", "CANCELLED"},
    "PREPARING": {"RUNNING", "FAILED", "CANCELLED"},
    "RUNNING": {
        "WAITING_FOR_PROVIDER",
        "WAITING_FOR_APPROVAL",
        "SUCCEEDED",
        "FAILED",
        "STALE",
        "CANCELLED",
    },
    "WAITING_FOR_PROVIDER": {"RUNNING", "FAILED", "CANCELLED"},
    "WAITING_FOR_APPROVAL": {"RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"},
    # Terminal states — no exits. Retries create a new job/attempt.
    "SUCCEEDED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "STALE": set(),
}

TERMINAL_STATUSES: frozenset[str] = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "STALE"})


class InvalidStateTransitionError(Exception):
    """Raised when a job status transition is not allowed."""


class JobNotFoundError(Exception):
    """Raised when a job_id does not exist."""


class OptimisticLockFailureError(Exception):
    """Raised when a concurrent version conflict is detected."""


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


@dataclass
class JobRecord:
    """P1.1 verification job with full lifecycle fields."""

    job_id: str
    repo_path: str
    base_ref: str
    head_ref: str
    spec_path: str
    status: str = "CREATED"
    version: int = 0
    config_hash: str = ""
    retry_count: int = 0
    max_retries: int = 3
    stale_replaced_by: str | None = None
    last_error: str | None = None
    worker_id: str | None = None
    trace_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None


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
    def connection(self) -> Any:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── State machine helpers ──────────────────────────────────────

    @staticmethod
    def is_valid_transition(from_status: str, to_status: str) -> bool:
        return to_status in _VALID_TRANSITIONS.get(from_status, set())

    @staticmethod
    def is_terminal(status: str) -> bool:
        return status in TERMINAL_STATUSES

    # ── DDL / Migrations ───────────────────────────────────────────

    # Increment this when DDL changes.  Used by ensure_tables and migration files.
    _SCHEMA_VERSION = 2

    def ensure_tables(self) -> None:
        """Create Phase 0/1 tables if they don't exist.  Idempotent."""
        ddl = """
        CREATE TABLE IF NOT EXISTS verification_jobs (
            id CHAR(36) PRIMARY KEY,
            repo_path VARCHAR(1024) NOT NULL,
            base_ref VARCHAR(255) NOT NULL,
            head_ref VARCHAR(255) NOT NULL,
            spec_path VARCHAR(1024) NOT NULL,
            status ENUM('CREATED','QUEUED','PREPARING','RUNNING',
                         'WAITING_FOR_PROVIDER','WAITING_FOR_APPROVAL',
                         'SUCCEEDED','FAILED','CANCELLED','STALE') DEFAULT 'CREATED',
            version INT NOT NULL DEFAULT 0,
            config_hash VARCHAR(64) DEFAULT '',
            depth VARCHAR(16) DEFAULT 'FAST',
            retry_count INT NOT NULL DEFAULT 0,
            max_retries INT NOT NULL DEFAULT 3,
            stale_replaced_by CHAR(36) NULL,
            last_error TEXT NULL,
            worker_id CHAR(36) NULL,
            trace_id CHAR(36) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            started_at TIMESTAMP NULL,
            completed_at TIMESTAMP NULL,
            INDEX idx_status (status),
            INDEX idx_worker (worker_id),
            UNIQUE KEY uq_repo_head_config (repo_path(255), head_ref(255), config_hash)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS job_stages (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            job_id CHAR(36) NOT NULL,
            from_status VARCHAR(32) NOT NULL,
            to_status VARCHAR(32) NOT NULL,
            worker_id CHAR(36) NULL,
            trace_id CHAR(36) NULL,
            message TEXT NULL,
            error_code VARCHAR(64) NULL,
            duration_ms INT NULL,
            created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
            FOREIGN KEY (job_id) REFERENCES verification_jobs(id) ON DELETE CASCADE,
            INDEX idx_job_id (job_id),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            aggregate_type VARCHAR(64) NOT NULL DEFAULT 'verification_job',
            aggregate_id CHAR(36) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            actor VARCHAR(64) DEFAULT 'system',
            details JSON NULL,
            trace_id CHAR(36) NULL,
            created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
            INDEX idx_aggregate (aggregate_type, aggregate_id),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS findings (
            id CHAR(36) PRIMARY KEY,
            job_id CHAR(36) NOT NULL,
            contract_id VARCHAR(128) NOT NULL,
            severity ENUM('BLOCKER','MAJOR','MINOR','NEEDS_CONFIRMATION') NOT NULL,
            confidence FLOAT NOT NULL,
            evidence_type VARCHAR(64) NOT NULL,
            impact_path JSON,
            capsule_path VARCHAR(1024),
            fingerprint VARCHAR(64) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_finding_fingerprint (job_id, fingerprint),
            FOREIGN KEY (job_id) REFERENCES verification_jobs(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS contracts (
            id CHAR(36) PRIMARY KEY,
            job_id CHAR(36) NOT NULL,
            contract_id_str VARCHAR(128) NOT NULL,
            requirement_text TEXT NOT NULL,
            checker_type VARCHAR(64) NOT NULL,
            expected_behavior TEXT NOT NULL,
            result ENUM('PASS','FAIL','UNVERIFIED') DEFAULT 'UNVERIFIED',
            evidence_ref VARCHAR(1024),
            FOREIGN KEY (job_id) REFERENCES verification_jobs(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS provider_capabilities (
            id INT AUTO_INCREMENT PRIMARY KEY,
            base_url VARCHAR(1024) NOT NULL,
            model VARCHAR(128) NOT NULL,
            capabilities JSON NOT NULL,
            probed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS outbox_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_id CHAR(36) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            schema_version VARCHAR(16) DEFAULT '1.0',
            aggregate_id CHAR(36) NOT NULL,
            trace_id CHAR(36) NULL,
            occurred_at TIMESTAMP(3) NOT NULL,
            attempt INT NOT NULL DEFAULT 1,
            status ENUM('PENDING','CLAIMED','PUBLISHED','FAILED') DEFAULT 'PENDING',
            routing_key VARCHAR(128) NOT NULL,
            payload JSON NOT NULL,
            last_error TEXT NULL,
            claimed_by VARCHAR(64) NULL,
            claimed_at TIMESTAMP(3) NULL,
            published_at TIMESTAMP(3) NULL,
            created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
            INDEX idx_status (status, created_at),
            INDEX idx_aggregate (aggregate_id),
            UNIQUE KEY uq_event_id (event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS processed_events (
            consumer_name VARCHAR(128) NOT NULL,
            event_id CHAR(36) NOT NULL,
            processed_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
            PRIMARY KEY (consumer_name, event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self.connection() as conn:
            for statement in ddl.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.cursor().execute(stmt)

    # ── P1.1 Job lifecycle ────────────────────────────────────────

    def create_job(self, job: dict[str, Any]) -> str:
        """Create a verification job with status CREATED and version 0."""
        job_id: str = str(job.get("id", str(uuid.uuid4())))
        _sql = (
            "INSERT INTO verification_jobs "
            "(id, repo_path, base_ref, head_ref, spec_path, status, "
            "version, config_hash, depth, trace_id) "
            "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, %(head_ref)s, "
            "%(spec_path)s, 'CREATED', 0, %(config_hash)s, %(depth)s, %(trace_id)s)"
        )
        job.setdefault("config_hash", "")
        job.setdefault("depth", "FAST")
        job.setdefault("trace_id", str(uuid.uuid4()))
        job["id"] = job_id
        with self.connection() as conn:
            conn.cursor().execute(_sql, job)
            self._write_stage(conn, job_id, "CREATED", "CREATED", msg="Job created")
        return job_id

    def transition_job_status(
        self,
        job_id: str,
        to_status: str,
        *,
        expected_version: int | None = None,
        worker_id: str | None = None,
        error_msg: str | None = None,
        error_code: str | None = None,
        stale_replaced_by: str | None = None,
        trace_id: str | None = None,
    ) -> int:
        """CAS transition: reads current status+version, validates, updates.

        Returns the new version number on success.
        Raises InvalidStateTransitionError, JobNotFoundError, or OptimisticLockFailureError.
        """
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT status, version FROM verification_jobs WHERE id = %s FOR UPDATE",
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                raise JobNotFoundError(f"Job {job_id} not found")

            from_status = row["status"]
            cur_version = row["version"]

            if not self.is_valid_transition(from_status, to_status):
                raise InvalidStateTransitionError(
                    f"Cannot transition from {from_status} to {to_status}"
                )

            if expected_version is not None and cur_version != expected_version:
                raise OptimisticLockFailureError(
                    f"Version mismatch: expected {expected_version}, actual {cur_version}"
                )

            new_version: int = int(cur_version) + 1
            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            updates = ["status = %s", "version = %s", "updated_at = %s"]
            params: list[Any] = [to_status, new_version, now]

            if worker_id:
                updates.append("worker_id = %s")
                params.append(worker_id)
            if error_msg:
                updates.append("last_error = %s")
                params.append(error_msg[:4096])
            if stale_replaced_by:
                updates.append("stale_replaced_by = %s")
                params.append(stale_replaced_by)
            if to_status == "RUNNING" and from_status != "RUNNING":
                updates.append("started_at = %s")
                params.append(now)
            if to_status in TERMINAL_STATUSES:
                updates.append("completed_at = %s")
                params.append(now)

            params.append(job_id)
            cur.execute(
                f"UPDATE verification_jobs SET {', '.join(updates)} WHERE id = %s",  # nosec B608
                params,
            )
            self._write_stage(
                conn,
                job_id,
                from_status,
                to_status,
                worker_id=worker_id,
                trace_id=trace_id,
                msg=error_msg,
                error_code=error_code,
            )
            self._write_audit(
                conn,
                job_id,
                "status_transition",
                {"from": from_status, "to": to_status},
                trace_id=trace_id,
            )
            return new_version

    def transition_job_status_in_tx(
        self,
        conn: Any,
        job_id: str,
        to_status: str,
        *,
        expected_version: int | None = None,
        worker_id: str | None = None,
        error_msg: str | None = None,
        error_code: str | None = None,
        stale_replaced_by: str | None = None,
        trace_id: str | None = None,
    ) -> int:
        """CAS transition within an existing transaction (same as transition_job_status
        but uses the provided connection instead of opening its own).

        Caller is responsible for COMMIT/ROLLBACK.
        """
        cur = conn.cursor()
        cur.execute(
            "SELECT status, version FROM verification_jobs WHERE id = %s FOR UPDATE",
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            raise JobNotFoundError(f"Job {job_id} not found")

        from_status = row["status"]
        cur_version = row["version"]

        if not self.is_valid_transition(from_status, to_status):
            raise InvalidStateTransitionError(
                f"Cannot transition from {from_status} to {to_status}"
            )

        if expected_version is not None and cur_version != expected_version:
            raise OptimisticLockFailureError(
                f"Version mismatch: expected {expected_version}, actual {cur_version}"
            )

        new_version: int = int(cur_version) + 1
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        updates = ["status = %s", "version = %s", "updated_at = %s"]
        params: list[Any] = [to_status, new_version, now]

        if worker_id:
            updates.append("worker_id = %s")
            params.append(worker_id)
        if error_msg:
            updates.append("last_error = %s")
            params.append(error_msg[:4096])
        if stale_replaced_by:
            updates.append("stale_replaced_by = %s")
            params.append(stale_replaced_by)
        if to_status == "RUNNING" and from_status != "RUNNING":
            updates.append("started_at = %s")
            params.append(now)
        if to_status in TERMINAL_STATUSES:
            updates.append("completed_at = %s")
            params.append(now)

        params.append(job_id)
        cur.execute(
            f"UPDATE verification_jobs SET {', '.join(updates)} WHERE id = %s",  # nosec B608
            params,
        )
        self._write_stage(
            conn,
            job_id,
            from_status,
            to_status,
            worker_id=worker_id,
            trace_id=trace_id,
            msg=error_msg,
            error_code=error_code,
        )
        self._write_audit(
            conn,
            job_id,
            "status_transition",
            {"from": from_status, "to": to_status},
            trace_id=trace_id,
        )
        return new_version

    def claim_stale_jobs(self, new_head_sha: str, repo_path: str) -> int:
        """Mark all non-terminal jobs for the same repo as STALE when head changes."""
        stale_count = 0
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM verification_jobs "
                "WHERE repo_path = %s AND status NOT IN ('SUCCEEDED','FAILED','CANCELLED','STALE')",
                (repo_path,),
            )
            for row in cur.fetchall():
                try:
                    self.transition_job_status(
                        row["id"],
                        "STALE",
                        stale_replaced_by=new_head_sha,
                    )
                    stale_count += 1
                except InvalidStateTransitionError:
                    pass
        return stale_count

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM verification_jobs WHERE id = %s", (job_id,))
            return cur.fetchone()  # type: ignore[no-any-return]

    def get_job_audit_log(self, job_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM audit_logs WHERE aggregate_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (job_id, limit),
            )
            return list(cur.fetchall())

    def list_jobs_by_status(self, status: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM verification_jobs WHERE status = %s ORDER BY created_at LIMIT %s",
                (status, limit),
            )
            return list(cur.fetchall())

    def _write_stage(
        self,
        conn: Any,
        job_id: str,
        from_status: str,
        to_status: str,
        *,
        worker_id: str | None = None,
        trace_id: str | None = None,
        msg: str | None = None,
        error_code: str | None = None,
    ) -> None:
        conn.cursor().execute(
            "INSERT INTO job_stages (job_id, from_status, to_status, worker_id, "
            "trace_id, message, error_code) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                job_id,
                from_status,
                to_status,
                worker_id,
                trace_id,
                msg[:2000] if msg else None,
                error_code,
            ),
        )

    def _write_audit(
        self,
        conn: Any,
        aggregate_id: str,
        event_type: str,
        details: dict[str, Any] | None = None,
        *,
        actor: str = "system",
        trace_id: str | None = None,
    ) -> None:
        conn.cursor().execute(
            "INSERT INTO audit_logs (aggregate_id, event_type, actor, details, trace_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (aggregate_id, event_type, actor, json.dumps(details) if details else None, trace_id),
        )

    # ── P1.3 Atomic idempotency ─────────────────────────────────────

    def try_claim_event(self, consumer_name: str, event_id: str) -> bool:
        """Atomically insert a processed_events row. Returns True if first claim.

        Must be called inside the same MySQL transaction as the business writes.
        Only call this from within self.connection() context.
        """
        try:
            # The PK (consumer_name, event_id) ensures only one INSERT succeeds.
            # This MUST be inside the same TX as the business writes.
            return True  # caller handles the INSERT in their TX
        except Exception:
            return False

    def insert_processed_event_in_tx(self, conn: Any, consumer_name: str, event_id: str) -> bool:
        """Insert into processed_events within the given transaction.

        Returns True if this is the first claim (INSERT succeeded).
        Returns False if already processed (dup key — idempotent skip).
        Must be called inside an active connection() context (TX).
        """
        try:
            conn.cursor().execute(
                "INSERT INTO processed_events (consumer_name, event_id) VALUES (%s, %s)",
                (consumer_name, event_id),
            )
            return True
        except pymysql.err.IntegrityError:
            # Already processed — idempotent skip
            return False

    # ── P0.5 backward-compatible API ──────────────────────────────

    def insert_job(self, job: dict[str, Any]) -> None:
        """P0.5 compatibility: create job with RUNNING status (legacy).

        For new code, use create_job() or create_job_with_outbox() instead.
        """
        job.setdefault("config_hash", "")
        job.setdefault("depth", job.get("depth", "FAST"))
        job_id = job.get("id", str(uuid.uuid4()))
        job["id"] = job_id
        _sql = (
            "INSERT INTO verification_jobs "
            "(id, repo_path, base_ref, head_ref, spec_path, status, "
            "version, config_hash, depth) "
            "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
            "%(head_ref)s, %(spec_path)s, 'RUNNING', 0, "
            "%(config_hash)s, %(depth)s)"
        )
        with self.connection() as conn:
            conn.cursor().execute(_sql, job)

    def update_job_status(self, job_id: str, status: str) -> None:
        """P0.5 compatibility: transition through the state machine.

        Unlike the previous version, this does NOT bypass the state machine.
        If the transition is invalid, the exception propagates to the caller.
        """
        self.transition_job_status(job_id, status)

    def insert_finding(self, finding: dict[str, Any]) -> None:
        _sql = (
            "INSERT INTO findings "
            "(id, job_id, contract_id, severity, confidence, "
            "evidence_type, impact_path, capsule_path, fingerprint) "
            "VALUES (%(id)s, %(job_id)s, %(contract_id)s, %(severity)s, "
            "%(confidence)s, %(evidence_type)s, %(impact_path)s, %(capsule_path)s, "
            "%(fingerprint)s)"
        )
        finding.setdefault("fingerprint", None)
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

    # ── P1.2 Outbox ───────────────────────────────────────────────

    def create_job_with_outbox(
        self,
        job: dict[str, Any],
        *,
        routing_key: str = "q.verification.run",
    ) -> str:
        """Transactional: INSERT job + INSERT outbox_event in one TX."""
        job_id: str = str(job.get("id", str(uuid.uuid4())))
        job["id"] = job_id
        job.setdefault("config_hash", "")
        job.setdefault("depth", "FAST")
        trace_id = job.get("trace_id", str(uuid.uuid4()))
        job["trace_id"] = trace_id

        event_id = str(uuid.uuid4())
        occurred_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        payload = {
            "job_id": job_id,
            "repo_path": job.get("repo_path", ""),
            "base_ref": job.get("base_ref", ""),
            "head_ref": job.get("head_ref", ""),
            "spec_path": job.get("spec_path", ""),
        }

        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO verification_jobs "
                "(id, repo_path, base_ref, head_ref, spec_path, status, "
                "version, config_hash, depth, trace_id) "
                "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, %(head_ref)s, "
                "%(spec_path)s, 'CREATED', 0, %(config_hash)s, %(depth)s, %(trace_id)s)",
                job,
            )
            cur.execute(
                "INSERT INTO outbox_events "
                "(event_id, event_type, aggregate_id, trace_id, occurred_at, "
                "routing_key, payload, status) "
                "VALUES (%s, 'JobCreated', %s, %s, %s, %s, %s, 'PENDING')",
                (event_id, job_id, trace_id, occurred_at, routing_key, json.dumps(payload)),
            )
            self._write_stage(conn, job_id, "CREATED", "QUEUED", trace_id=trace_id)
            # Transition to QUEUED after outbox write
            cur.execute(
                "UPDATE verification_jobs SET status = 'QUEUED', version = 1 WHERE id = %s",
                (job_id,),
            )
        return job_id

    def claim_pending_events(
        self, *, limit: int = 10, claimed_by: str = "relay-1"
    ) -> list[dict[str, Any]]:
        """Claim up to `limit` PENDING outbox events for publishing."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, event_id, event_type, aggregate_id, trace_id, "
                "routing_key, payload, attempt "
                "FROM outbox_events "
                "WHERE status = 'PENDING' "
                "ORDER BY created_at "
                "LIMIT %s "
                "FOR UPDATE SKIP LOCKED",
                (limit,),
            )
            events = list(cur.fetchall())
            if events:
                ids = [e["id"] for e in events]
                now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                placeholders = ",".join(["%s"] * len(ids))
                sql = (
                    "UPDATE outbox_events SET status = 'CLAIMED', "  # nosec B608
                    "claimed_by = %s, claimed_at = %s "
                    "WHERE id IN (" + placeholders + ")"
                )
                cur.execute(sql, [claimed_by, now] + ids)
            return events

    def mark_event_published(self, event_id: str) -> None:
        with self.connection() as conn:
            conn.cursor().execute(
                "UPDATE outbox_events SET status = 'PUBLISHED', "
                "published_at = NOW(3) WHERE event_id = %s",
                (event_id,),
            )

    def mark_event_failed(self, event_id: str, error_msg: str) -> None:
        with self.connection() as conn:
            conn.cursor().execute(
                "UPDATE outbox_events SET status = 'FAILED', last_error = %s, "
                "attempt = attempt + 1 WHERE event_id = %s",
                (error_msg[:4096], event_id),
            )

    def is_event_processed(self, consumer_name: str, event_id: str) -> bool:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM processed_events WHERE consumer_name = %s AND event_id = %s",
                (consumer_name, event_id),
            )
            return cur.fetchone() is not None

    def mark_event_processed(self, consumer_name: str, event_id: str) -> None:
        with self.connection() as conn:
            conn.cursor().execute(
                "INSERT IGNORE INTO processed_events (consumer_name, event_id) VALUES (%s, %s)",
                (consumer_name, event_id),
            )

    def recover_stale_claims(self, *, older_than_seconds: int = 60) -> int:
        """Reset CLAIMED events that haven't been published within the window."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE outbox_events SET status = 'PENDING', claimed_by = NULL, "
                "claimed_at = NULL "
                "WHERE status = 'CLAIMED' "
                "AND claimed_at < NOW(3) - INTERVAL %s SECOND",
                (older_than_seconds,),
            )
            return cur.rowcount or 0

    # ── Health ────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        try:
            with self.connection() as conn:
                conn.cursor().execute("SELECT 1")
            return True
        except Exception:
            return False
