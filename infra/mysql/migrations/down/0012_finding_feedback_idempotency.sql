-- 0012 down: remove the (finding_id, created_by) bound.
--
-- The dedupe 0012 performed is not restorable: superseded verdict rows were
-- deleted to satisfy the key. Reverting therefore drops the constraint and
-- leaves the surviving rows as they are.

ALTER TABLE finding_feedback DROP INDEX uniq_feedback_finding_actor;
