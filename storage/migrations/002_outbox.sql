-- SpecProof P1.2: Transactional Outbox Migration
-- Creates the outbox table for reliable event publication.

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
