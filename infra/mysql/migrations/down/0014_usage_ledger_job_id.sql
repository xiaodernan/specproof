-- Down for 0014_usage_ledger_job_id.sql (manual rollback only - the runner
-- never applies files under down/). Drops the per-job attribution column and
-- its index: every row loses its job_id (the lifecycle event_ids still embed
-- the job; LLM token rows lose the job dimension entirely), so the #230
-- read path must be rolled back alongside this migration.

ALTER TABLE usage_ledger DROP INDEX idx_usage_tenant_job;

ALTER TABLE usage_ledger DROP COLUMN job_id;
