-- 0002: extend the job state machine to 10 states
-- (adds CANCELLED for user cancellation and WAITING_FOR_PROVIDER for
-- recoverable provider outages) and add the audit log table (P0-A5).

ALTER TABLE verification_jobs
    MODIFY status ENUM('PENDING','QUEUED','RUNNING','WAITING_FOR_PROVIDER',
                       'VERIFIED','BLOCKED','STALE','FAILED','CANCELLED',
                       'ERROR') DEFAULT 'PENDING';

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id CHAR(36) NULL,
    actor VARCHAR(128) NOT NULL,
    action VARCHAR(64) NOT NULL,
    from_status VARCHAR(32) NULL,
    to_status VARCHAR(32) NULL,
    detail VARCHAR(1024) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_job (job_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
