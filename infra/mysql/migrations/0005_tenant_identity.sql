-- 0005: multi-tenant identity (industrialization phase 1,
-- docs/architecture/MULTI_TENANT_DESIGN.md §3) — tenants / users / scoped
-- api_tokens, plus the tenant ownership columns on verification_jobs and
-- audit_logs (attempted_tenant) for the §2 isolation/audit rules.
--
-- Up/down pairing convention: the matching down migration lives in
-- infra/mysql/migrations/down/0005_tenant_identity.sql (the runner only
-- applies *.sql directly under this directory, so the down file is never
-- auto-applied; ops run it manually to roll back).
--
-- Timestamps are epoch-second DOUBLE columns — the same portable convention
-- as storage/identity.py (the MySqlIdentityStore backend), so the
-- migration-created schema and ensure_schema() converge on one layout.

CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    plan_id VARCHAR(64) NOT NULL DEFAULT 'free',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DOUBLE NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    email VARCHAR(255) NOT NULL,
    oidc_sub VARCHAR(255),
    role VARCHAR(32) NOT NULL DEFAULT 'viewer',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at DOUBLE NOT NULL,
    UNIQUE KEY uq_users_tenant_email (tenant_id, email),
    UNIQUE KEY uq_users_oidc_sub (oidc_sub),
    INDEX idx_users_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS api_tokens (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    name VARCHAR(128) NOT NULL,
    token_hash CHAR(64) NOT NULL,
    secret_hash VARCHAR(128) NOT NULL,
    scopes VARCHAR(1024) NOT NULL DEFAULT '',
    expires_at DOUBLE,
    last_used_at DOUBLE,
    created_at DOUBLE NOT NULL,
    UNIQUE KEY uq_tokens_hash (token_hash),
    INDEX idx_tokens_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE verification_jobs
    ADD COLUMN tenant_id CHAR(36) NULL,
    ADD INDEX idx_jobs_tenant (tenant_id);

ALTER TABLE audit_logs
    ADD COLUMN attempted_tenant VARCHAR(128) NULL;
