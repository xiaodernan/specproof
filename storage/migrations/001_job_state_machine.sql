-- SpecProof P1.1: Job State Machine Migration
-- Replaces the 5-state ENUM with 8 states, adds retry/stale/worker columns.
-- Migration is idempotent: safe to run multiple times.

ALTER TABLE verification_jobs
  MODIFY COLUMN status ENUM(
    'PENDING',
    'QUEUED',
    'RUNNING',
    'VERIFIED',
    'BLOCKED',
    'STALE',
    'FAILED',
    'ERROR'
  ) NOT NULL DEFAULT 'PENDING';

-- Add new columns (IF NOT EXISTS not supported in MySQL 8.4 for ALTER TABLE,
-- but ADD COLUMN is idempotent-safe because the migration framework checks first)
ALTER TABLE verification_jobs
  ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_retries INT NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS stale_replaced_by CHAR(36) NULL,
  ADD COLUMN IF NOT EXISTS last_error TEXT NULL,
  ADD COLUMN IF NOT EXISTS worker_id CHAR(36) NULL;

-- Add index for worker claim queries
ALTER TABLE verification_jobs
  ADD INDEX IF NOT EXISTS idx_status (status),
  ADD INDEX IF NOT EXISTS idx_worker (worker_id);
