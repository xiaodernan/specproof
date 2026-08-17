"""P2 integration tests — contract registry against live MySQL (skip-safe)."""

import hashlib
import uuid

import pytest

from agent.contracts.compiler import ContractCandidate
from agent.contracts.registry import ContractRegistry
from storage.mysql import MySQLStore

REPO = "test-repo-" + uuid.uuid4().hex[:8]


@pytest.fixture()
def registry():
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
    return ContractRegistry(store)


def _candidate() -> ContractCandidate:
    return ContractCandidate(
        id="test-HTTP-01",
        checker_type="http",
        requirement="Endpoints must require authentication",
        requirement_ref="REQ-AUTH-01",
        expected_behavior="Unauthenticated requests must receive 401",
        source="spec",
    )


def test_propose_approve_read_roundtrip(registry):
    digest = hashlib.sha256(b"spec-v1").hexdigest()[:16]
    written = registry.upsert_candidates(REPO, digest, [_candidate()])
    assert written == 1

    rows = registry.list_contracts(REPO)
    assert len(rows) == 1
    assert rows[0]["status"] == "PROPOSED"

    # Not yet approved → nothing for the pipeline.
    assert registry.get_approved_for_repo(REPO, digest) == []

    assert registry.approve("test-HTTP-01", "alice", "looks right")
    approved = registry.get_approved_for_repo(REPO, digest)
    assert len(approved) == 1
    assert approved[0].approved is True
    assert approved[0].checker_type == "http"


def test_approval_does_not_transfer_across_spec_versions(registry):
    digest_v1 = hashlib.sha256(b"spec-v1").hexdigest()[:16]
    digest_v2 = hashlib.sha256(b"spec-v2").hexdigest()[:16]
    registry.upsert_candidates(REPO, digest_v1, [_candidate()])
    registry.approve("test-HTTP-01", "alice")

    # Different spec digest → the old approval must NOT apply.
    assert registry.get_approved_for_repo(REPO, digest_v2) == []
    # Same digest → still approved.
    assert len(registry.get_approved_for_repo(REPO, digest_v1)) == 1


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
