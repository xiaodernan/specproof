-- 0004: GitHub Check Run bookkeeping for jobs created from PR events.
-- NULL = job not sourced from a GitHub PR (CLI / local runs).

ALTER TABLE verification_jobs
    ADD COLUMN github_check_json JSON NULL;
