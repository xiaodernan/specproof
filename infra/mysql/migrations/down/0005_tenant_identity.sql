-- 0005 DOWN (manual rollback; the MigrationRunner never applies files
-- under down/). Reverses infra/mysql/migrations/0005_tenant_identity.sql:
-- drops the identity tables and the tenant ownership columns.

DROP TABLE IF EXISTS api_tokens;

DROP TABLE IF EXISTS users;

DROP TABLE IF EXISTS tenants;

ALTER TABLE verification_jobs
    DROP INDEX idx_jobs_tenant,
    DROP COLUMN tenant_id;

ALTER TABLE audit_logs
    DROP COLUMN attempted_tenant;
