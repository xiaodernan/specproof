-- 0003: persist pipeline summaries per job (dashboard + audit view).

ALTER TABLE verification_jobs
    ADD COLUMN summary JSON NULL;
