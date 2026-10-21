-- Down migration for 0017_contract_observes_keys.sql.
--
-- The column is dropped outright. What it held is the key families a
-- contract version DECLARED, and that declaration is still in the
-- spec the version was compiled from — so a rolled-back database
-- loses the stored copy, not the declaration itself. The approved
-- version's declaration then has to be re-derived from the spec text
-- at run time, which is the behaviour that existed before 0017.

ALTER TABLE contract_registry
    DROP COLUMN observes_keys;
