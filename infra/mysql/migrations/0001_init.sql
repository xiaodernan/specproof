-- 0001: initial schema (jobs, findings, contracts, capabilities,
-- registry, approvals, outbox). Fresh installs only.

CREATE TABLE IF NOT EXISTS verification_jobs (
    id CHAR(36) PRIMARY KEY,
    repo_path VARCHAR(512) NOT NULL,
    base_ref VARCHAR(255) NOT NULL,
    head_ref VARCHAR(255) NOT NULL,
    spec_path VARCHAR(1024) NOT NULL,
    status ENUM('PENDING','QUEUED','RUNNING','VERIFIED','BLOCKED',
                  'STALE','FAILED','ERROR') DEFAULT 'PENDING',
    depth VARCHAR(16) DEFAULT 'FAST',
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    stale_replaced_by CHAR(36) NULL,
    last_error TEXT NULL,
    worker_id CHAR(36) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_worker (worker_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS findings (
    id CHAR(36) PRIMARY KEY,
    job_id CHAR(36) NOT NULL,
    contract_id VARCHAR(128) NOT NULL,
    severity ENUM('BLOCKER','MAJOR','MINOR','NEEDS_CONFIRMATION') NOT NULL,
    confidence FLOAT NOT NULL,
    evidence_type VARCHAR(64) NOT NULL,
    impact_path JSON,
    capsule_path VARCHAR(1024),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES verification_jobs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS contracts (
    id CHAR(36) PRIMARY KEY,
    job_id CHAR(36) NOT NULL,
    contract_id_str VARCHAR(128) NOT NULL,
    requirement_text TEXT NOT NULL,
    checker_type VARCHAR(64) NOT NULL,
    expected_behavior TEXT NOT NULL,
    result ENUM('PASS','FAIL','UNVERIFIED') DEFAULT 'UNVERIFIED',
    evidence_ref VARCHAR(1024),
    FOREIGN KEY (job_id) REFERENCES verification_jobs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS provider_capabilities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    base_url VARCHAR(1024) NOT NULL,
    model VARCHAR(128) NOT NULL,
    capabilities JSON NOT NULL,
    probed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS contract_registry (
    id VARCHAR(128) PRIMARY KEY,
    repo_path VARCHAR(512) NOT NULL,
    requirement_ref VARCHAR(64) NOT NULL,
    requirement TEXT NOT NULL,
    checker_type VARCHAR(64) NOT NULL,
    expected_behavior TEXT NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'spec',
    version INT NOT NULL DEFAULT 1,
    status ENUM('PROPOSED','APPROVED','REJECTED','REVOKED') DEFAULT 'PROPOSED',
    spec_digest VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_repo (repo_path),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS contract_approvals (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    contract_id VARCHAR(128) NOT NULL,
    action ENUM('APPROVE','REJECT','REVOKE') NOT NULL,
    approved_by VARCHAR(128) NOT NULL,
    reason VARCHAR(1024) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES contract_registry(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    aggregate_id CHAR(36) NOT NULL,
    aggregate_type VARCHAR(64) NOT NULL DEFAULT 'verification_job',
    event_type VARCHAR(64) NOT NULL,
    payload JSON NOT NULL,
    routing_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    published_at TIMESTAMP(3) NULL,
    retry_count INT NOT NULL DEFAULT 0,
    INDEX idx_published (published_at, id),
    INDEX idx_aggregate (aggregate_type, aggregate_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
