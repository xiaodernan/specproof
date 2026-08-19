"""W38 unit tests — contract immutable versioning (§A task 6).

No Docker, no network: every registry test runs the REAL registry code
paths on InMemoryContractStorage (the same seam the production MySQL
backend implements). Covers:

- checker_version stamping per checker module;
- append-only versioning (edits create a NEW version, never mutate);
- mutation of a stored version raises ContractVersionError;
- approvals bind an exact (contract_id, version) and audit that pair;
- lineage nodes/edges reference exact contract versions;
- legacy contracts without version keys keep historical lineage ids.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from agent.checkers import constitution as constitution_module
from agent.checkers import java_source as java_module
from agent.checkers import schema_and_tests as schema_module
from agent.contracts.compiler import ContractCandidate, compile_candidates
from agent.contracts.parser import parse_requirements
from agent.contracts.records import (
    DEFAULT_CHECKER_VERSION,
    ContractRecord,
    ContractVersionError,
    checker_version_for,
)
from agent.contracts.registry import ContractRegistry
from agent.contracts.storage import DuplicateVersionError, InMemoryContractStorage
from evidence.lineage import build_lineage, verify_lineage

REPO = "repo-w38"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _candidate(**overrides: object) -> ContractCandidate:
    fields: dict[str, object] = {
        "id": "AUTH-01",
        "checker_type": "http",
        "requirement": "Endpoints must require authentication",
        "requirement_ref": "REQ-AUTH-01",
        "expected_behavior": "Unauthenticated requests must receive 401",
        "source": "spec",
    }
    fields.update(overrides)
    return ContractCandidate(**fields)  # type: ignore[arg-type]


@pytest.fixture()
def registry() -> ContractRegistry:
    return ContractRegistry(InMemoryContractStorage())


# ── checker_version stamping ──────────────────────────────────────────────


def test_checker_modules_declare_stable_checker_version():
    assert java_module.CHECKER_VERSION == "2.0.0"
    assert constitution_module.CHECKER_VERSION == "1.0.0"
    assert schema_module.CHECKER_VERSION == "1.0.0"


def test_checker_version_resolution_is_stable():
    assert checker_version_for("http") == java_module.CHECKER_VERSION
    assert checker_version_for("sql") == java_module.CHECKER_VERSION
    assert checker_version_for("constitution") == constitution_module.CHECKER_VERSION
    assert checker_version_for("tests") == schema_module.CHECKER_VERSION
    # Unknown families degrade to the documented stable default, never a guess.
    assert checker_version_for("bogus") == DEFAULT_CHECKER_VERSION
    assert checker_version_for("") == DEFAULT_CHECKER_VERSION


def test_compiled_candidates_carry_checker_version_and_default_version():
    parsed = parse_requirements(
        "1. Authentication\n   - Must reject unauthenticated requests with 401.\n",
    )
    candidates = compile_candidates(parsed.requirements)
    assert candidates
    for candidate in candidates:
        assert candidate.version == 1
        assert candidate.checker_version == checker_version_for(candidate.checker_type)


# ── append-only versioning ────────────────────────────────────────────────


def test_first_propose_creates_version_one(registry):
    written = registry.upsert_candidates(REPO, _digest("spec-v1"), [_candidate()])
    assert written == 1
    versions = registry.list_versions("AUTH-01")
    assert [v.version for v in versions] == [1]
    assert versions[0].status == "PROPOSED"
    assert versions[0].checker_version == checker_version_for("http")


def test_repropose_identical_content_is_idempotent_and_keeps_status(registry):
    digest = _digest("spec-v1")
    assert registry.upsert_candidates(REPO, digest, [_candidate()]) == 1
    assert registry.approve("AUTH-01", "alice", version=1)
    # Identical content + identical spec: idempotent no-op — the approval
    # must never be silently downgraded by a re-propose.
    assert registry.upsert_candidates(REPO, digest, [_candidate()]) == 0
    versions = registry.list_versions("AUTH-01")
    assert [v.version for v in versions] == [1]
    assert versions[0].status == "APPROVED"


def test_changed_spec_appends_new_version_and_never_mutates_the_old(registry):
    digest_v1 = _digest("spec-v1")
    digest_v2 = _digest("spec-v2")
    registry.upsert_candidates(REPO, digest_v1, [_candidate()])
    original = registry.get_contract_record("AUTH-01", 1)
    assert original is not None

    changed = _candidate(
        requirement="Endpoints must require stronger authentication",
        expected_behavior="Unauthenticated requests must receive 401 or 403",
    )
    assert registry.upsert_candidates(REPO, digest_v2, [changed]) == 1

    versions = registry.list_versions("AUTH-01")
    assert [v.version for v in versions] == [1, 2]
    # The stored version 1 is byte-for-byte what it was — append-only.
    stored_v1 = registry.get_contract_record("AUTH-01", 1)
    assert stored_v1 is not None
    assert stored_v1.content_fields() == original.content_fields()
    assert stored_v1.status == "PROPOSED"
    assert stored_v1.spec_digest == digest_v1
    # Version 2 carries the new content and starts as a fresh PROPOSAL.
    stored_v2 = registry.get_contract_record("AUTH-01", 2)
    assert stored_v2 is not None
    assert stored_v2.spec_digest == digest_v2
    assert stored_v2.status == "PROPOSED"
    assert stored_v2.expected_behavior == changed.expected_behavior


def test_storage_seam_is_append_only(registry):
    storage = InMemoryContractStorage()
    storage.insert_version({
        "id": "X-01", "repo_path": REPO, "requirement_ref": "R",
        "requirement": "r", "checker_type": "sql",
        "expected_behavior": "e", "source": "spec",
        "spec_digest": "a" * 16, "checker_version": "1.0.0",
        "version": 1, "status": "PROPOSED",
    })
    with pytest.raises(DuplicateVersionError):
        storage.insert_version({
            "id": "X-01", "repo_path": REPO, "requirement_ref": "R",
            "requirement": "r2", "checker_type": "sql",
            "expected_behavior": "e2", "source": "spec",
            "spec_digest": "b" * 16, "checker_version": "1.0.0",
            "version": 1, "status": "PROPOSED",
        })


# ── mutation guard ────────────────────────────────────────────────────────


def test_mutation_of_stored_version_raises(registry):
    registry.upsert_candidates(REPO, _digest("spec-v1"), [_candidate()])
    with pytest.raises(ContractVersionError) as excinfo:
        registry.mutate_version("AUTH-01", 1, expected_behavior="hacked")
    message = str(excinfo.value)
    assert "immutable" in message
    assert "propose a new version" in message
    # The guard fired and nothing changed.
    stored = registry.get_contract_record("AUTH-01", 1)
    assert stored is not None
    assert stored.expected_behavior == _candidate().expected_behavior


def test_approval_transitions_do_not_mutate_content(registry):
    registry.upsert_candidates(REPO, _digest("spec-v1"), [_candidate()])
    before = registry.get_contract_record("AUTH-01", 1)
    assert before is not None
    assert registry.approve("AUTH-01", "alice", "ok", version=1)
    after = registry.get_contract_record("AUTH-01", 1)
    assert after is not None
    assert before.content_fields() == after.content_fields()
    assert after.status == "APPROVED"


# ── approval binds an exact version ───────────────────────────────────────


def test_approval_binds_exact_version_and_does_not_transfer(registry):
    digest_v1 = _digest("spec-v1")
    digest_v2 = _digest("spec-v2")
    registry.upsert_candidates(REPO, digest_v1, [_candidate()])
    registry.upsert_candidates(
        REPO, digest_v2, [_candidate(expected_behavior="401 or 403")],
    )

    assert registry.approve("AUTH-01", "alice", "ok", version=1)
    # Audit row records the exact (contract_id, version) pair.
    audit = [r for r in registry.approval_rows() if r["action"] == "APPROVE"]
    assert [(r["contract_id"], r["contract_version"]) for r in audit] == [("AUTH-01", 1)]
    # Only the exact approved version becomes enforceable.
    approved_v1 = registry.get_approved_for_repo(REPO, digest_v1)
    assert [c.version for c in approved_v1] == [1]
    assert approved_v1[0].checker_version == checker_version_for("http")
    assert registry.get_approved_for_repo(REPO, digest_v2) == []
    # Re-approving the same version is a rejected CAS, not a new audit row.
    assert not registry.approve("AUTH-01", "alice", "ok", version=1)
    assert len(registry.approval_rows()) == 1


def test_approve_defaults_to_newest_version(registry):
    digest_v2 = _digest("spec-v2")
    registry.upsert_candidates(REPO, _digest("spec-v1"), [_candidate()])
    registry.upsert_candidates(
        REPO, digest_v2, [_candidate(expected_behavior="401 or 403")],
    )
    assert registry.approve("AUTH-01", "bob")
    audit = registry.approval_rows()
    assert audit[0]["contract_version"] == 2
    assert [c.version for c in registry.get_approved_for_repo(REPO, digest_v2)] == [2]


def test_reject_and_revoke_bind_versions_independently(registry):
    digest_v1 = _digest("spec-v1")
    digest_v2 = _digest("spec-v2")
    registry.upsert_candidates(REPO, digest_v1, [_candidate()])
    registry.upsert_candidates(
        REPO, digest_v2, [_candidate(expected_behavior="401 or 403")],
    )
    assert registry.reject("AUTH-01", "carol", "too vague", version=2)
    assert not registry.reject("AUTH-01", "carol", "too vague", version=2)
    assert registry.approve("AUTH-01", "alice", version=1)
    assert registry.revoke("AUTH-01", "alice", "policy change", version=1)
    # v2 was rejected then re-approved independently of v1's lifecycle.
    assert registry.approve("AUTH-01", "alice", version=2)
    assert registry.get_approved_for_repo(REPO, digest_v1) == []
    assert [c.version for c in registry.get_approved_for_repo(REPO, digest_v2)] == [2]


def test_approve_unknown_version_returns_false(registry):
    registry.upsert_candidates(REPO, _digest("spec-v1"), [_candidate()])
    assert not registry.approve("AUTH-01", "alice", version=7)
    assert not registry.approve("MISSING-01", "alice")


# ── ContractRecord semantics ──────────────────────────────────────────────


def test_contract_record_roundtrip_and_content_key():
    record = ContractRecord(
        contract_id="AUTH-01",
        version=2,
        checker_version="2.0.0",
        checker_type="http",
        requirement="r",
        requirement_ref="REQ-1",
        expected_behavior="e",
        source="spec",
        spec_digest="a" * 16,
        status="APPROVED",
    )
    clone = ContractRecord.from_row(record.to_dict())
    assert clone == record
    assert clone.content_equal(record)
    assert clone.content_key() == record.content_key()
    candidate = record.to_candidate()
    assert candidate.id == "AUTH-01"
    assert candidate.version == 2
    assert candidate.checker_version == "2.0.0"
    assert candidate.approved is True
    with pytest.raises(ContractVersionError):
        ContractRecord(contract_id="X", version=0)
    with pytest.raises(ContractVersionError):
        ContractRecord(contract_id="X", status="SIDEWAYS")


# ── lineage references exact versions ─────────────────────────────────────


def _lineage_context(version: int | None = 2, checker_version: str | None = "2.0.0"):
    contract: dict[str, object] = {
        "id": "AUTH-01",
        "checker_type": "http",
        "requirement": "auth required",
        "expected_behavior": "401 without token",
        "approved": True,
    }
    if version is not None:
        contract["version"] = version
    if checker_version is not None:
        contract["checker_version"] = checker_version
    return {
        "requirement_text": "Only authenticated users may change the email.",
        "contracts": [contract],
        "static_findings": [{
            "contract_id": "AUTH-01",
            "type": "static",
            "description": "annotation dropped",
            "evidence_type": "static_analysis",
            "severity": "MAJOR",
            "confidence": 0.8,
            "location": "SecurityConfig.java",
        }],
        "confirmed_findings": [{
            "id": "F-1",
            "contract_id": "AUTH-01",
            "severity": "MAJOR",
            "confidence": 0.9,
            "evidence_type": "differential_execution",
            "evidence_digest": "sha256:" + "3" * 64,
            "source": "differential",
            "description": "regression",
        }],
    }


def test_lineage_nodes_and_edges_reference_exact_versions():
    dag, root = build_lineage(_lineage_context(), built_at="2026-08-18T00:00:00+00:00")
    ids = {node["id"]: node for node in dag["nodes"]}
    contract_node = ids["contract:AUTH-01@v2"]
    assert contract_node["kind"] == "contract_version"
    assert contract_node["meta"]["version"] == 2
    assert contract_node["meta"]["checker_version"] == "2.0.0"
    # checker + finding edges point at the EXACT versioned node.
    for edge in dag["edges"]:
        if edge["source"].startswith(("checker:", "finding:")):
            assert edge["target"] == "contract:AUTH-01@v2"
    ok, diffs = verify_lineage(dag, root)
    assert ok and diffs == []


def test_lineage_root_changes_when_version_changes():
    fixed_ts = "2026-08-18T00:00:00+00:00"
    _dag1, root_v2 = build_lineage(_lineage_context(version=2), built_at=fixed_ts)
    _dag2, root_v3 = build_lineage(_lineage_context(version=3), built_at=fixed_ts)
    assert root_v2 != root_v3


def test_lineage_tampered_version_node_detected():
    dag, root = build_lineage(_lineage_context(), built_at="2026-08-18T00:00:00+00:00")
    payload = {
        "nodes": [
            {**node, "id": "contract:AUTH-01@v9"}
            if node["id"] == "contract:AUTH-01@v2"
            else node
            for node in dag["nodes"]
        ],
        "edges": list(dag["edges"]),
    }
    ok, diffs = verify_lineage(payload, root)
    assert not ok
    # Renaming the version node orphans every edge that referenced it —
    # verify_lineage reports the dangling edges (and the node id feeds the
    # root leaf list, so the rewrite is also caught on a clean re-verify).
    assert any(d.get("kind") == "dangling_edge" for d in diffs)


def test_lineage_legacy_contracts_keep_historical_ids():
    # Contracts without version keys produce the historical node id and
    # no version metadata — pre-existing lineage documents stay stable.
    dag, _root = build_lineage(
        _lineage_context(version=None, checker_version=None),
        built_at="2026-08-18T00:00:00+00:00",
    )
    contract_node = next(
        node for node in dag["nodes"] if node["kind"] == "contract_version"
    )
    assert contract_node["id"] == "contract:AUTH-01"
    assert "version" not in contract_node["meta"]
    assert "checker_version" not in contract_node["meta"]
    for edge in dag["edges"]:
        if edge["source"].startswith(("checker:", "finding:")):
            assert edge["target"] == "contract:AUTH-01"


def test_lineage_serialized_payload_carries_version_meta():
    from evidence.lineage import deserialize_lineage, lineage_to_json

    dag, root = build_lineage(_lineage_context(), built_at="2026-08-18T00:00:00+00:00")
    payload = json.loads(lineage_to_json(dag, root))
    dag2, root2 = deserialize_lineage(payload)
    assert root2 == root
    assert verify_lineage(dag2, root2)[0]
