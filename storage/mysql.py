"""MySQL store — business truth for Phase 0."""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pymysql
from pymysql.cursors import DictCursor


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

    def ensure_tables(self) -> None:
        """Create Phase 0 minimal tables if they don't exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS verification_jobs (
            id CHAR(36) PRIMARY KEY,
            repo_path VARCHAR(1024) NOT NULL,
            base_ref VARCHAR(255) NOT NULL,
            head_ref VARCHAR(255) NOT NULL,
            spec_path VARCHAR(1024) NOT NULL,
            status ENUM('PENDING','RUNNING','VERIFIED','BLOCKED','ERROR') DEFAULT 'PENDING',
            depth VARCHAR(16) DEFAULT 'FAST',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
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
        """
        with self.connection() as conn:
            for statement in ddl.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.cursor().execute(stmt)

    def insert_job(self, job: dict[str, Any]) -> None:
        _sql = (
            "INSERT INTO verification_jobs "
            "(id, repo_path, base_ref, head_ref, spec_path, status, depth) "
            "VALUES (%(id)s, %(repo_path)s, %(base_ref)s, "
            "%(head_ref)s, %(spec_path)s, %(status)s, %(depth)s)"
        )
        with self.connection() as conn:
            conn.cursor().execute(_sql, job)

    def update_job_status(self, job_id: str, status: str) -> None:
        with self.connection() as conn:
            conn.cursor().execute(
                "UPDATE verification_jobs SET status = %s WHERE id = %s",
                (status, job_id),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            conn.cursor().execute(
                "SELECT * FROM verification_jobs WHERE id = %s", (job_id,)
            )
            return conn.cursor().fetchone()

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
