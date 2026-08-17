"""P2 unit tests — contract candidate compiler + family mapping."""

from agent.contracts.compiler import (
    candidates_from_constitution,
    compile_candidates,
    dedupe_candidates,
    family_id_for,
)
from agent.contracts.parser import parse_requirements

SPEC = """1. Authentication
   - Must reject unauthenticated requests with 401.

2. Transactional integrity
   - Email update must be atomic with token invalidation.
"""


def test_compile_candidates_from_spec():
    parsed = parse_requirements(SPEC)
    candidates = compile_candidates(parsed.requirements)
    types = {c.checker_type for c in candidates}
    assert "http" in types
    assert "sql" in types
    for c in candidates:
        assert c.result == "UNVERIFIED"
        assert not c.approved  # candidates are proposals, not contracts


def test_family_mapping():
    assert family_id_for("http", "must reject unauthenticated requests") == "AUTH-01"
    assert family_id_for("sql", "must be atomic within a transaction") == "TRANSACTION-01"
    assert family_id_for("sql", "email must be unique") == "UNIQUE-01"
    assert family_id_for("redis", "old tokens must be invalidated") == "TOKEN_INVALIDATION-01"
    assert family_id_for("openapi", "api must stay compatible") == "BACKWARD_COMPATIBLE-01"
    assert family_id_for("rabbitmq", "event exactly once") == "EVENT_ONCE-01"


def test_constitution_rules_become_candidates():
    policy = ["Repository policy:\n- Must keep all endpoints authenticated.\n"]
    candidates = candidates_from_constitution(policy)
    assert len(candidates) == 1
    assert candidates[0].source == "constitution"
    assert candidates[0].checker_type == "http"


def test_dedupe_merges_equivalent_behaviours():
    parsed = parse_requirements(SPEC)
    spec_cands = compile_candidates(parsed.requirements)
    policy = ["- Must reject unauthenticated requests with 401.\n"]
    const_cands = candidates_from_constitution(policy)
    merged = dedupe_candidates(spec_cands + const_cands)
    http_rows = [c for c in merged if c.checker_type == "http"]
    assert len(http_rows) == 1
    assert http_rows[0].source == "spec"  # spec beats constitution
