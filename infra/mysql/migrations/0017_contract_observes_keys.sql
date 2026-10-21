-- 0017: keep the declared key families with the contract version.
--
-- A requirement can DECLARE which Redis key families it is about
-- ("observes keys: user:cache:*"). Since #368 that declaration is a
-- STRUCTURED field of the spec language, and the compiled contract
-- carries it as `observes_keys`.
--
-- The registry is the place where a human APPROVED a contract version.
-- If the declaration is not stored with the version, the approved
-- contract has to have its declaration re-derived from the CURRENT spec
-- text at run time — and a spec that changed after the approval would
-- silently change what the approved contract is observed against. The
-- approved version has to keep the declaration it was approved with.
--
-- The column is JSON (a list of key patterns) and NULL for rows
-- written before this migration: "this version declared nothing" is a
-- real state, and it is different from "this version declared keys we
-- lost".
--
-- It is NOT a content column for change detection: the spec digest
-- already covers "the spec changed" (a changed spec already creates a
-- new version), so the declaration rides along with the version it was
-- compiled into.

ALTER TABLE contract_registry
    ADD COLUMN observes_keys JSON NULL;
