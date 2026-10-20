-- 0015: extend the job state machine to the Phase 1 frozen vocabulary.
--
-- The frozen state machine (storage/mysql.py) names five states the ENUM
-- did not have:
--
--   PREPARING        the job is building its Base/Head worktrees
--   CONTRACT_REVIEW  the job is waiting for a human to approve contracts
--   REVIEWING        the differential has run; the Review Court decides
--   NEEDS_REVIEW     terminal: the evidence is insufficient, a human judges
--   EXPIRED          terminal: the job passed its execution deadline
--
-- Without this the writes are not merely REJECTED: a non-strict MySQL
-- truncates an unknown ENUM value to '' — a silent corruption that would
-- leave the row in a status no reader can interpret and no reclaimer can
-- find. That is the same class of failure this project's red lines are
-- about, so the schema and the code move together.
--
-- The existing values keep their ORDINALS (only new ones are appended), so
-- anything that stored an ENUM ordinal stays valid. The default moves
-- from 'PENDING' to 'QUEUED' because a new submission is QUEUED: the
-- legacy PENDING name survives as a status the state machine still
-- accepts, but nothing creates it any more.
--
-- Forward compatibility: MODIFY is re-appliable — a second run is a no-op.
-- Up/down pairing: infra/mysql/migrations/down/0015_job_state_vocabulary.sql
-- (the runner only applies *.sql directly under this directory).

ALTER TABLE verification_jobs
    MODIFY status ENUM('PENDING','QUEUED','RUNNING','WAITING_FOR_PROVIDER',
                       'VERIFIED','BLOCKED','STALE','FAILED','CANCELLED',
                       'ERROR',
                       'PREPARING','CONTRACT_REVIEW','REVIEWING',
                       'NEEDS_REVIEW','EXPIRED') DEFAULT 'QUEUED';
