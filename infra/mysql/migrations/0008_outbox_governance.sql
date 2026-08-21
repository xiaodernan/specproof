-- 0008: outbox governance columns (主计划 §14.2, storage/ data &
-- reliability). Extends the outbox table with the fields the relay needs
-- to govern publication:
--
--   tenant_id       row ownership for multi-tenant relay stats/cleanup
--   payload_digest  sha256 of the payload JSON (payload_digest() format)
--   publish_count   total publish attempts (successes and failures)
--   last_error      most recent publish failure (truncated by the store)
--   next_retry_at   per-row retry deferral; the relay only claims rows
--                   whose next_retry_at is NULL or in the past
--   dead_lettered_at  DLQ state; rows past max_retries are dead-lettered
--                   and excluded from polling instead of retried forever
--
-- Forward compatibility: every new column is nullable or defaulted, so
-- rows written before 0008 project cleanly under the new code, and old
-- relay builds simply ignore the columns. No existing column is changed.
--
-- Up/down pairing: the matching down migration lives in
-- infra/mysql/migrations/down/0008_outbox_governance.sql (the runner only
-- applies *.sql directly under this directory, so the down file is never
-- auto-applied; ops run it manually to roll back).

ALTER TABLE outbox
    ADD COLUMN tenant_id VARCHAR(36) NULL AFTER aggregate_type,
    ADD COLUMN payload_digest VARCHAR(80) NULL AFTER payload,
    ADD COLUMN publish_count INT NOT NULL DEFAULT 0 AFTER retry_count,
    ADD COLUMN last_error VARCHAR(1000) NULL AFTER publish_count,
    ADD COLUMN next_retry_at TIMESTAMP(3) NULL AFTER last_error,
    ADD COLUMN dead_lettered_at TIMESTAMP(3) NULL AFTER next_retry_at,
    ADD INDEX idx_outbox_tenant (tenant_id),
    ADD INDEX idx_outbox_dead (dead_lettered_at, published_at, id);
