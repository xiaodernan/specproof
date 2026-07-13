-- 002_failed_terminal.sql — FAILED is now terminal (no exits)
--
-- Changes:
--   - FAILED transitions from {QUEUED, CANCELLED} → {} (terminal).
--   - Retries must now create a new job_id via create_job_with_outbox().
--   - Already applied in code (_VALID_TRANSITIONS in mysql.py).
--     This file exists for audit trail and production deployment.
--
-- Run:  mysql -u specproof -p < 002_failed_terminal.sql
-- Safe: no DDL changes needed — this is a behavioural-only migration.
--       All existing FAILED jobs remain FAILED.

-- Verify no FAILED jobs have open non-terminal exit paths:
-- SELECT id, status FROM verification_jobs WHERE status = 'FAILED';

-- The application layer now enforces:
--   1. FAILED → QUEUED  is REJECTED (InvalidStateTransitionError)
--   2. FAILED → CANCELLED is REJECTED (InvalidStateTransitionError)
--   3. FAILED → any other status is REJECTED
--   4. To retry: create_job_with_outbox() with a new job_id.
