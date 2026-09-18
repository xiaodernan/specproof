-- Dashboard timeline and recent-job reads use bounded created_at ranges.
-- Cover both single-tenant deployments and tenant-scoped workspaces.
ALTER TABLE verification_jobs
    ADD INDEX idx_jobs_created_id (created_at, id),
    ADD INDEX idx_jobs_tenant_created_id (tenant_id, created_at, id);
