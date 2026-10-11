-- 0014: per-job metered-usage attribution (#230, the ledger slice of
-- "per-job cost accounting").
--
-- usage_ledger rows carried their job only inside event_id (the verify/craft
-- lifecycle events), while LLM token rows carried no job dimension at all, so
-- no query could answer "what did this job spend?". job_id is now a
-- first-class column:
--
--   the metering writer stamps it (lifecycle hooks pass their job, and
--   TokenBudget entries stamp theirs before the billing projection);
--   GET /api/v1/billing/jobs/{job_id} reads it back per job;
--   rows written before this migration read back as '' (unattributed),
--   never a guess.
--
-- The column is NOT NULL DEFAULT '': MySQL has no ADD COLUMN IF NOT EXISTS,
-- so this one-shot migration is the only schema writer for EXISTING
-- databases (storage/billing.py's CREATE TABLE covers fresh ones, and its
-- CREATE INDEX IF NOT EXISTS matches idx_usage_tenant_job on both paths).
-- Forward compatibility: every non-key value is defaulted.
-- Up/down pairing: infra/mysql/migrations/down/0014_usage_ledger_job_id.sql
-- (the runner only applies *.sql directly under this directory).

ALTER TABLE usage_ledger
    ADD COLUMN job_id VARCHAR(255) NOT NULL DEFAULT '';

ALTER TABLE usage_ledger
    ADD INDEX idx_usage_tenant_job (tenant_id, job_id);
