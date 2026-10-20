-- 0016: give every verification job an execution deadline.
--
-- Until now a job could only be reclaimed when its WORKER died (the lease
-- TTL expired). A job whose worker is alive but wedged — a sandbox that
-- never returns, a test that hangs forever — has no deadline at all: it
-- sits in an in-flight status until someone notices by hand.
--
-- `max_execution_seconds` is the total budget for ONE attempt, measured
-- from the moment the job was created. It is per-job (not a global
-- constant) so a DEEP run and a FAST run can carry different budgets,
-- and it is a COLUMN (not a setting) so an operator can widen a single
-- stuck job's budget without touching every other row.
--
-- The DEFAULT is the FAST-path budget. A DEEP job gets more room
-- through the same column when it is submitted; until then it inherits
-- the default and the reaper says so honestly rather than pretending it
-- had a budget nobody set.
--
-- The EXPIRED terminal state itself already exists (migration 0015); this
-- migration only supplies the number the expiry check measures against.
--
-- Forward compatibility: the column is NOT NULL with a default, so a row
-- written by an older worker (which does not know the column) still
-- lands with a usable budget instead of NULL — "no deadline" would be
-- indistinguishable from "the deadline is far away".

ALTER TABLE verification_jobs
    ADD COLUMN max_execution_seconds INT NOT NULL DEFAULT 3600;
