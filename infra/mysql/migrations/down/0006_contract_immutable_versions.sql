-- 0006 down: restore the single-version contract_registry shape.
-- Only the highest stored version per contract id survives — matching
-- the pre-0006 data shape. Run this ONLY when no new-version rows matter.

ALTER TABLE contract_approvals
    DROP FOREIGN KEY fk_contract_approvals_version;

DELETE FROM contract_approvals WHERE contract_version > 1;

ALTER TABLE contract_approvals
    DROP INDEX idx_contract_approvals_version,
    DROP COLUMN contract_version;

DELETE FROM contract_registry WHERE version > 1;

ALTER TABLE contract_registry
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (id),
    DROP INDEX idx_contract_registry_id,
    DROP COLUMN checker_version;

-- The FK that 0006 dropped by name (contract_approvals_ibfk_1) must come back,
-- with that exact name: an FK cannot be dropped by a name it does not carry, so
-- without this line the up migration is not re-runnable after this down, and
-- `contract_approvals` is left referencing nothing at all — a rollback that
-- silently discards 0001's referential integrity while claiming to restore the
-- pre-0006 shape. Restored LAST, because the target column (id) is only the
-- sole primary key of contract_registry again once the ALTER above has run.
ALTER TABLE contract_approvals
    ADD CONSTRAINT contract_approvals_ibfk_1
    FOREIGN KEY (contract_id) REFERENCES contract_registry (id) ON DELETE CASCADE;
