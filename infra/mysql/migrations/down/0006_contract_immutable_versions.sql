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
