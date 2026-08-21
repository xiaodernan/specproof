-- 0007: tenant billing & usage ledger (industrialization phase 6,
-- docs/architecture/BILLING_DESIGN.md) — billing_plans /
-- billing_subscriptions / usage_ledger (idempotent by unique event_id) /
-- invoices (draft→issued→paid), with tenant ownership columns and the
-- per-tenant monthly invoice key.
--
-- Up/down pairing convention: the matching down migration lives in
-- infra/mysql/migrations/down/0007_tenant_billing.sql (the runner only
-- applies *.sql directly under this directory, so the down file is never
-- auto-applied; ops run it manually to roll back). The 0006 slot is owned
-- by the W38 contract-versions lane, so billing takes 0007.
--
-- Timestamps are epoch-second DOUBLE columns — the same portable
-- convention as storage/billing.py (the MySqlBillingStore backend), so
-- the migration-created schema and ensure_schema() converge on one
-- layout. quotas/overage/line_items are JSON columns; every value travels
-- through placeholders in the store layer (bandit B608-safe statements).

CREATE TABLE IF NOT EXISTS billing_plans (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price_monthly DOUBLE NOT NULL DEFAULT 0,
    quotas JSON NOT NULL,
    overage JSON NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS billing_subscriptions (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    plan_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    period_start DOUBLE NOT NULL,
    period_end DOUBLE NOT NULL,
    INDEX idx_billing_subs_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS usage_ledger (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    metric VARCHAR(32) NOT NULL,
    units DOUBLE NOT NULL,
    unit_label VARCHAR(64) NOT NULL DEFAULT '',
    happened_at DOUBLE NOT NULL,
    UNIQUE KEY uq_usage_event (event_id),
    INDEX idx_usage_tenant_time (tenant_id, happened_at),
    INDEX idx_usage_tenant_metric (tenant_id, metric)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    period VARCHAR(7) NOT NULL,
    line_items JSON NOT NULL,
    total DOUBLE NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    UNIQUE KEY uq_invoices_tenant_period (tenant_id, period),
    INDEX idx_invoices_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
