"""P2 integration tests — contract registry against live MySQL (skip-safe).

§A task 6: also covers the append-only versioning semantics against the
real composite PRIMARY KEY (id, version) added by migration 0006.
"""

import hashlib
import uuid

import pytest

from agent.contracts.compiler import ContractCandidate
from agent.contracts.registry import ContractRegistry
from agent.contracts.storage import MySQLContractStorage
from storage.mysql import MySQLStore

REPO = "test-repo-" + uuid.uuid4().hex[:8]


@pytest.fixture()
def registry() -> ContractRegistry:
    store = MySQLStore()
    try:
        store.ensure_tables()
        with store.connection() as conn:
            conn.cursor().execute(
                "DELETE FROM contract_approvals WHERE contract_id LIKE %s",
                ("test-%",),
            )
            conn.cursor().execute(
                "DELETE FROM contract_registry WHERE repo_path LIKE %s",
                ("test-%",),
            )
    except Exception:
        pytest.skip("MySQL not available")
    return ContractRegistry(MySQLContractStorage(store))


def _candidate(**overrides: object) -> ContractCandidate:
    fields: dict[str, object] = {
        "id": "test-HTTP-01",
        "checker_type": "http",
        "requirement": "Endpoints must require authentication",
        "requirement_ref": "REQ-AUTH-01",
        "expected_behavior": "Unauthenticated requests must receive 401",
        "source": "spec",
    }
    fields.update(overrides)
    return ContractCandidate(**fields)  # type: ignore[arg-type]


def test_propose_approve_read_roundtrip(registry):
    digest = hashlib.sha256(b"spec-v1").hexdigest()[:16]
    written = registry.upsert_candidates(REPO, digest, [_candidate()])
    assert written == 1

    rows = registry.list_contracts(REPO)
    assert len(rows) == 1
    assert rows[0]["status"] == "PROPOSED"
    assert rows[0]["checker_version"]

    # Not yet approved → nothing for the pipeline.
    assert registry.get_approved_for_repo(REPO, digest) == []

    assert registry.approve("test-HTTP-01", "alice", "looks right")
    approved = registry.get_approved_for_repo(REPO, digest)
    assert len(approved) == 1
    assert approved[0].approved is True
    assert approved[0].checker_type == "http"
    assert approved[0].version == 1


def test_approval_does_not_transfer_across_spec_versions(registry):
    digest_v1 = hashlib.sha256(b"spec-v1").hexdigest()[:16]
    digest_v2 = hashlib.sha256(b"spec-v2").hexdigest()[:16]
    registry.upsert_candidates(REPO, digest_v1, [_candidate()])
    registry.approve("test-HTTP-01", "alice")

    # A changed spec APPENDS version 2 (append-only) instead of mutating v1.
    registry.upsert_candidates(
        REPO, digest_v2, [_candidate(expected_behavior="401 or 403")],
    )
    assert [v.version for v in registry.list_versions("test-HTTP-01")] == [1, 2]
    # Different spec digest → the old approval must NOT apply.
    assert registry.get_approved_for_repo(REPO, digest_v2) == []
    # Same digest → still approved, bound to the exact version 1.
    assert [c.version for c in registry.get_approved_for_repo(REPO, digest_v1)] == [1]


def test_reject_and_approve_again(registry):
    digest = hashlib.sha256(b"spec-v1").hexdigest()[:16]
    registry.upsert_candidates(REPO, digest, [_candidate()])
    assert registry.reject("test-HTTP-01", "bob", "too vague")
    assert not registry.reject("test-HTTP-01", "bob")  # already rejected
    assert registry.approve("test-HTTP-01", "alice")  # rejected → approvable


def test_revoke_approved(registry):
    digest = hashlib.sha256(b"spec-v1").hexdigest()[:16]
    registry.upsert_candidates(REPO, digest, [_candidate()])
    registry.approve("test-HTTP-01", "alice")
    assert registry.revoke("test-HTTP-01", "alice", "policy changed")
    assert registry.get_approved_for_repo(REPO, digest) == []


def test_approval_binds_exact_version_in_audit_table(registry):
    digest = hashlib.sha256(b"spec-v1").hexdigest()[:16]
    registry.upsert_candidates(REPO, digest, [_candidate()])
    registry.approve("test-HTTP-01", "alice", "ok", version=1)
    audit = registry.approval_rows()
    assert [(r["contract_id"], r["contract_version"]) for r in audit] == [
        ("test-HTTP-01", 1),
    ]
    assert not registry.approve("test-HTTP-01", "alice", version=7)
