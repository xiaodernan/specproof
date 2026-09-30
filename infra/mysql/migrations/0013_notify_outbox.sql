-- 0013: notification outbox (§16.6-1, reliable webhook delivery).
--
-- The worker's terminal hook previously sent webhooks directly (best-effort,
-- in-process): a crash between the accepted terminal write and the HTTP POST
-- lost the notification with no trace beyond a counter. This table persists
-- the BUILT notification payload so a relay can deliver it at-least-once
-- with the same governance the job-event outbox got in 0008:
--
--   delivered_at     NULL until the relay confirms the endpoint accepted it
--   attempts         total delivery attempts (successes and failures)
--   last_error       most recent delivery failure (truncated by the store)
--   next_retry_at    per-row retry deferral; the relay only claims rows
--                    whose next_retry_at is NULL or in the past
--   dead_lettered_at DLQ state; rows past max_retries are dead-lettered
--                    and excluded from polling instead of retried forever
--
-- The payload is the notification AS BUILT at enqueue time (event_type /
-- title / text / blocks): delivery reproduces the exact announcement the
-- terminal verdict earned, immune to later template edits.
--
-- Forward compatibility: every non-key column is nullable or defaulted.
-- Up/down pairing: infra/mysql/migrations/down/0013_notify_outbox.sql
-- (the runner only applies *.sql directly under this directory).

CREATE TABLE IF NOT EXISTS notify_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id CHAR(36) NOT NULL,
    verdict VARCHAR(32) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    delivered_at TIMESTAMP(3) NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error VARCHAR(1000) NULL,
    next_retry_at TIMESTAMP(3) NULL,
    dead_lettered_at TIMESTAMP(3) NULL,
    INDEX idx_notify_claim (dead_lettered_at, delivered_at, id),
    INDEX idx_notify_job (job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
