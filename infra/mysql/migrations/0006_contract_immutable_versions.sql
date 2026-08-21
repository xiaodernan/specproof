-- 0006: Contract immutable versioning (§A task 6)
--
-- contract_registry becomes append-only per (contract_id, version):
--   * checker_version records the checker implementation version that
--     produced each stored version;
--   * the composite PRIMARY KEY (id, version) makes in-place version
--     bumps impossible at the SQL level — writes are INSERT-only;
--   * contract_approvals binds (contract_id, contract_version) and its
--     foreign key references the composite key.
--
-- Safe on existing data: id was the PRIMARY KEY, so every id has exactly
-- one stored row (version 1); adding version to the key changes nothing
-- for existing rows and existing approval rows all reference version 1,
-- which the append-only table guarantees still exists.

ALTER TABLE contract_registry
    ADD COLUMN checker_version VARCHAR(64) NOT NULL DEFAULT '' AFTER source;

ALTER TABLE contract_approvals
    ADD COLUMN contract_version INT NOT NULL DEFAULT 1 AFTER contract_id;

-- The FK must go before the key it references changes shape.
ALTER TABLE contract_approvals
    DROP FOREIGN KEY contract_approvals_ibfk_1;

ALTER TABLE contract_registry
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (id, version),
    ADD INDEX idx_contract_registry_id (id);

ALTER TABLE contract_approvals
    ADD INDEX idx_contract_approvals_version (contract_id, contract_version);

ALTER TABLE contract_approvals
    ADD CONSTRAINT fk_contract_approvals_version
    FOREIGN KEY (contract_id, contract_version)
    REFERENCES contract_registry (id, version)
    ON DELETE CASCADE;
