ALTER TABLE verification_jobs
    DROP INDEX idx_jobs_tenant_created_id,
    DROP INDEX idx_jobs_created_id;
