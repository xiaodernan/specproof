-- 0018: an index for the provider-wait sweeps (status, then park time).
--
-- The worker sweeps WAITING_FOR_PROVIDER rows on a timer
-- (reclaim_stale_running / recover_waiting_for_provider_jobs, #71/#74):
--   SELECT ... WHERE status = 'WAITING_FOR_PROVIDER' [AND updated_at < ...]
--   ORDER BY updated_at, id
-- With only idx_status(status), MySQL filters by status and then SORTS the
-- survivors -- "Using index condition; Using filesort" in EXPLAIN, measured
-- on this box before this migration. The sweep runs every 300s, so the
-- sort is paid over and over on a table that only grows.
--
-- (status, updated_at, id) lets the same read walk the index in order and
-- stop at the limit: no filesort, and the park-age predicate is a range
-- on the second column.
--
-- The index is deliberately NOT (status, created_at, id): the sweep orders by
-- the park time (updated_at), not by the creation time.

ALTER TABLE verification_jobs
    ADD INDEX idx_jobs_status_updated_id (status, updated_at, id);
