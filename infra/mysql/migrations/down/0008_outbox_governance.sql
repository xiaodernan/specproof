-- 0008 DOWN (manual rollback; the MigrationRunner never applies
-- files under down/). Reverses
-- infra/mysql/migrations/0008_outbox_governance.sql: drops the governance
-- columns and their indexes. Rows dead-lettered while the columns existed
-- revert to plain unpublished rows (retryable again), and the per-row
-- next_retry_at deferral falls back to the relay loop backoff — the same
-- at-least-once semantics as before 0008.

ALTER TABLE outbox
    DROP INDEX idx_outbox_dead,
    DROP INDEX idx_outbox_tenant,
    DROP COLUMN dead_lettered_at,
    DROP COLUMN next_retry_at,
    DROP COLUMN last_error,
    DROP COLUMN publish_count,
    DROP COLUMN payload_digest,
    DROP COLUMN tenant_id;
