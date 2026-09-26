-- 0012: make one verdict mean one verdict (finding_feedback idempotency).
--
-- Go/No-Go gate 13 reads acceptance_rate out of this table as
-- accepted / (accepted + rejected). The 0009 schema put no bound on how many
-- rows one person could file for one finding, and the POST route generated a
-- fresh UUID every call, so the same reviewer double-clicking the accept
-- button twice counted twice in the numerator. Nothing in the product
-- prevented that; measured 2026-09-26 the table had 0 rows in both real
-- schemas only because there is no UI for it at all (roadmap item 84).
--
-- Intent per 0009 header: one verdict per (finding, reviewer). A reviewer who
-- changes their mind overwrites their own verdict, and does not add weight.
--
-- Step 1 keeps the newest row per (finding_id, created_by) and drops the
-- older ones - the dedupe rule is the same rule the unique key is about to
-- enforce, so a database that already accumulated doubles converges on the
-- verdict its reviewer last stated instead of failing the migration.
-- Step 2 adds the bound.
--
-- Re-appliability is deliberate: MySQL commits DDL implicitly, so the ALTER
-- cannot share a transaction with step 1 or with the schema_migrations row.
-- Measured 2026-09-26 when this migration's connection died mid-flight: the
-- index existed while version 12 did not, and a naive second run failed
-- with error 1061. Both steps are therefore written so a second run
-- converges - step 1 finds nothing left to delete, step 2 is tolerated as
-- "already applied" by MigrationRunner._execute.
-- Down migration: down/0012_finding_feedback_idempotency.sql (manual, never
-- auto-applied).

DELETE f1 FROM finding_feedback f1
JOIN finding_feedback f2
ON f1.finding_id = f2.finding_id
AND f1.created_by = f2.created_by
AND (f1.created_at < f2.created_at
OR (f1.created_at = f2.created_at AND f1.id < f2.id));

ALTER TABLE finding_feedback
ADD UNIQUE KEY uniq_feedback_finding_actor (finding_id, created_by);
