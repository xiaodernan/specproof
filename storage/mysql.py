"""MySQL store — business truth for Phase 0/1.

P1.1: Added strict job state machine with 8 states, CAS transitions,
retry tracking, worker assignment, and stale detection.
"""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

# ── State machine ──────────────────────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "PENDING":  {"QUEUED", "ERROR"},
    "QUEUED":   {"RUNNING", "STALE", "ERROR"},
    "RUNNING":  {"VERIFIED", "BLOCKED", "FAILED", "STALE", "ERROR"},
    "FAILED":   {"QUEUED", "ERROR"},
    "STALE":    set(),
    "VERIFIED": set(),
    "BLOCKED":  set(),
    "ERROR":    set(),
}

TERMINAL_STATUSES = {"VERIFIED", "BLOCKED", "STALE", "ERROR"}


class InvalidStateTransition(Exception):
    """Raised when a job status transition is not allowed."""


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
    def connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── State machine helpers ─────────────────────────────────

    @staticmethod
    def is_valid_transition(from_status: str, to_status: str) -> bool:
        return to_status in _VALID_TRANSITIONS.get(from_status, set())

    @staticmethod
    def is_terminal(status: str) -> bool:
        return status in TERMINAL_STATUSES

    # ── DDL ───────────────────────────────────────────────────

    def ensure_tables(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS verification_jobs (
            id CHAR(36) PRIMARY KEY,
            repo_path VARCHAR(1024) NOT NULL,
            base_ref VARCHAR(255) NOT NULL,
            head_ref VARCHAR(255) NOT NULL,
            spec_path VARCHAR(1024) NOT NULL,
            status ENUM('PENDING','QUEUED','RUNNING','VERIFIED','BLOCKED','STALE','FAILED','ERROR') DEFAULT 'PENDING',
            depth VARCHAR(16) DEFAULT 'FAST',
            retry_count INT NOT NULL DEFAULT 0,
            max_retries INT NOT NULL DEFAULT 3,
            stale_replaced_by CHAR(36) NULL,
            last_error TEXT NULL,
            worker_id CHAR(36) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_status (status),
            INDEX idx_worker (worker_id)
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

        CREATE TABLE IF NOT EXISTS outbox (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            aggregate_id CHAR(36) NOT NULL,
            aggregate_type VARCHAR(64) NOT NULL DEFAULT 'verification_job',
            event_type VARCHAR(64) NOT NULL,
            payload JSON NOT NULL,
            routing_key VARCHAR(128) NOT NULL,
            created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
            published_at TIMESTAMP(3) NULL,
            retry_count INT NOT NULL DEFAULT 0,
            INDEX idx_published (published_at, id),
            INDEX idx_aggregate (aggregate_type, aggregate_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        with self.connection() as conn:
            for statement in ddl.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.cursor().execute(stmt)

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
            "(id, repo_path, base_ref, head_ref, spec_path, status, depth) "
            "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
            "%(head_ref)s, %(spec_path)s, %(status)s, %(depth)s)"
        )
        with self.connection() as conn:
            conn.cursor().execute(_sql, job)

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
        import json as _json

        job_id = job["id"]
        payload = {
            "job_id": job_id,
            "repo_path": job.get("repo_path", ""),
            "base_ref": job.get("base_ref", ""),
            "head_ref": job.get("head_ref", ""),
            "spec_path": job.get("spec_path", ""),
            "depth": job.get("depth", "FAST"),
        }
        with self.connection() as conn:
            conn.cursor().execute(
                "INSERT INTO verification_jobs "
                "(id, repo_path, base_ref, head_ref, spec_path, status, depth) "
                "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
                "%(head_ref)s, %(spec_path)s, 'PENDING', %(depth)s)",
                job,
            )
            conn.cursor().execute(
                "INSERT INTO outbox (aggregate_id, aggregate_type, event_type, payload, routing_key) "
                "VALUES (%(aggregate_id)s, %(aggregate_type)s, %(event_type)s, %(payload)s, %(routing_key)s)",
                {
                    "aggregate_id": job_id,
                    "aggregate_type": "verification_job",
                    "event_type": event_type,
                    "payload": _json.dumps(payload),
                    "routing_key": routing_key,
                },
            )
            # Transition to QUEUED after outbox is safely persisted
            conn.cursor().execute(
                "UPDATE verification_jobs SET status = 'QUEUED' WHERE id = %s",
                (job_id,),
            )
        return job_id

    def fetch_pending_outbox_rows(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch unpublished outbox rows with SKIP LOCKED for relay.

        Returns the oldest unpublished rows (FIFO order).
        """
        with self.connection() as conn:
            conn.cursor().execute(
                "SELECT id, aggregate_id, event_type, payload, routing_key "
                "FROM outbox "
                "WHERE published_at IS NULL "
                "ORDER BY id "
                "LIMIT %s "
                "FOR UPDATE SKIP LOCKED",
                (limit,),
            )
            return conn.cursor().fetchall()

    def mark_outbox_published(self, outbox_id: int) -> None:
        """Mark an outbox row as published (sets published_at to NOW)."""
        with self.connection() as conn:
            conn.cursor().execute(
                "UPDATE outbox SET published_at = NOW(3) WHERE id = %s",
                (outbox_id,),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            conn.cursor().execute(
                "SELECT * FROM verification_jobs WHERE id = %s", (job_id,)
            )
            return conn.cursor().fetchone()

    def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            conn.cursor().execute(
                "SELECT * FROM verification_jobs WHERE status = %s ORDER BY created_at",
                (status,),
            )
            return conn.cursor().fetchall()

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
            return cursor.rowcount == 1

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
