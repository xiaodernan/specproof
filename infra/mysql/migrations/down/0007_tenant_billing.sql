-- 0007 DOWN (manual rollback; the MigrationRunner never applies files
-- under down/). Reverses infra/mysql/migrations/0007_tenant_billing.sql:
-- drops the billing tables. The usage ledger and invoices are derived
-- data (rebuilt from the outbox events on the next billing cycle), so
-- the rollback loses no source-of-truth records.

DROP TABLE IF EXISTS invoices;

DROP TABLE IF EXISTS usage_ledger;

DROP TABLE IF EXISTS billing_subscriptions;

DROP TABLE IF EXISTS billing_plans;
