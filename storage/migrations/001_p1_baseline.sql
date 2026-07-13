-- 001_p1_baseline.sql — P0.5 → P1 baseline migration
-- Applies the full P1 reliability kernel schema.
--
-- Run: mysql -u specproof -p < 001_p1_baseline.sql
-- Rollback: DROP the new tables and ALTER the old columns back.
-- Idempotent: all DDL uses IF NOT EXISTS / IF EXISTS safe guard.

-- (1) New tables added in P1 ─────────────────────────────────────────

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

-- (2) Migrate existing verification_jobs to P1 schema ────────────────

-- Add P1 columns (safe: all have defaults or NULL)
ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 0;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS config_hash VARCHAR(64) DEFAULT '';

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS depth VARCHAR(16) DEFAULT 'FAST';

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS max_retries INT NOT NULL DEFAULT 3;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS stale_replaced_by CHAR(36) NULL;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS last_error TEXT NULL;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS worker_id CHAR(36) NULL;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS trace_id CHAR(36) NULL;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS started_at TIMESTAMP NULL;

ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP NULL;

-- Extend status ENUM with P1 states
ALTER TABLE verification_jobs
  MODIFY COLUMN status ENUM(
    'CREATED','QUEUED','PREPARING','RUNNING',
    'WAITING_FOR_PROVIDER','WAITING_FOR_APPROVAL',
    'SUCCEEDED','FAILED','CANCELLED','STALE'
  ) DEFAULT 'CREATED';

-- Add P1 indexes and constraints
ALTER TABLE verification_jobs
  ADD INDEX IF NOT EXISTS idx_status (status);

ALTER TABLE verification_jobs
  ADD INDEX IF NOT EXISTS idx_worker (worker_id);

ALTER TABLE verification_jobs
  ADD UNIQUE KEY IF NOT EXISTS uq_repo_head_config
    (repo_path(255), head_ref(255), config_hash);
