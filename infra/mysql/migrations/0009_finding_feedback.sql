-- 0009: finding feedback (Go/No-Go #13 mechanism).
--
-- Records the pilot users' accept/reject verdict per BLOCKER/MAJOR finding,
-- plus the reason for rejections. Gate #13 measures acceptance_rate from
-- this table: accepted / (accepted + rejected) across pilot repositories;
-- findings without feedback are never counted (silence is not acceptance).
--
-- Forward compatibility: a new table only — no existing column changes.
-- Findings without feedback simply have no rows here. Down migration:
-- infra/mysql/migrations/down/0009_finding_feedback.sql (manual, never
-- auto-applied by the runner).

CREATE TABLE IF NOT EXISTS finding_feedback (
    id CHAR(36) PRIMARY KEY,
    job_id CHAR(36) NOT NULL,
    tenant_id VARCHAR(36) NULL,
    finding_id CHAR(36) NOT NULL,
    contract_id VARCHAR(128) NOT NULL,
    severity ENUM('BLOCKER','MAJOR','MINOR','NEEDS_CONFIRMATION') NOT NULL,
    verdict ENUM('accept','reject') NOT NULL,
    reason VARCHAR(1000) NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_feedback_job (job_id),
    INDEX idx_feedback_tenant (tenant_id),
    FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
