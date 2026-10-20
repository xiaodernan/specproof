-- Down migration for 0015_job_state_vocabulary.sql.
--
-- The five states the up migration added do not exist in the old ENUM, so
-- the ENUM cannot be narrowed while any row still holds one: a non-strict
-- MySQL would truncate those rows to '' — the silent corruption the up
-- migration exists to prevent.
--
-- The rows are therefore folded into states the old ENUM has BEFORE the
-- column is narrowed:
--
--   PREPARING / CONTRACT_REVIEW / REVIEWING  → RUNNING   (in flight)
--   NEEDS_REVIEW                             → FAILED   (a human decision
--                                                          is still owed; FAILED
--                                                          says "not verified")
--   EXPIRED                                  → FAILED   (the deadline passed)
--
-- FAILED is the honest old-vocabulary landing for a terminal state that
-- is not VERIFIED/BLOCKED: the old ENUM had no other way to say "this
-- job did not pass". A NEEDS_REVIEW row folded into FAILED reads as
-- "not verified" — which is true — and the row keeps its last_error for
-- the reason.

UPDATE verification_jobs SET status = 'RUNNING'
  WHERE status IN ('PREPARING', 'CONTRACT_REVIEW', 'REVIEWING');

UPDATE verification_jobs SET status = 'FAILED'
  WHERE status IN ('NEEDS_REVIEW', 'EXPIRED');

ALTER TABLE verification_jobs
    MODIFY status ENUM('PENDING','QUEUED','RUNNING','WAITING_FOR_PROVIDER',
                       'VERIFIED','BLOCKED','STALE','FAILED','CANCELLED',
                       'ERROR') DEFAULT 'PENDING';
