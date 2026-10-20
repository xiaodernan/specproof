-- Down migration for 0016_job_execution_deadline.sql.
--
-- The column is dropped outright. Nothing is lost by that: the values it
-- held were a per-job budget the expiry check measured against, and the
-- EXPIRED rows it produced are already terminal facts in the job's own
-- last_error. Rolling the column back makes those jobs un-expirable
-- again (the reaper has no budget to measure), which is the pre-0016
-- behaviour — the same behaviour the up migration was written to
-- improve.

ALTER TABLE verification_jobs
    DROP COLUMN max_execution_seconds;
