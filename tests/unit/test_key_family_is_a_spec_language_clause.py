"""The key-family declaration is part of the SPEC LANGUAGE (#368).

Until now "observes keys: user:cache:*" was a line of prose that the
COLLECTORS re-parsed: `experiments/external_state.py` carried its own
copy of the syntax, so the spec's vocabulary leaked into the code that
observes the world.

The syntax now lives in one place — the spec language
(`agent/contracts/parser.py`) — and everything downstream reads a
FIELD:

- the parser lifts the declaration into `Requirement.observes_keys`;
- the compiler carries it into the contract candidate;
- `compile_contracts` puts it on every contract (empty when nothing is
  declared);
- the collector prefers the field, and only falls back to the prose
  declaration (through the spec language) for contracts that do not
  carry it yet — which is why NO migration window is needed: the old
  specs keep working exactly as before.
"""

from __future__ import annotations

from typing import Any

from agent.contracts.compiler import compile_candidates
from agent.contracts.parser import declared_key_patterns, parse_requirements
from agent.nodes.compile_contracts import compile_contracts_node
from experiments.external_state import key_patterns_for

SPEC = """1. Cache invalidation
The cached user entry must be evicted when the profile is written.
observes keys: user:cache:*

2. Token invalidation
The old session token must be deleted after an email change.
observes keys: token:user:*
"""


# ── the spec language owns the syntax ─────────────────────────────────────


def test_the_parser_lifts_the_declaration_into_a_field() -> None:
    parsed = parse_requirements(SPEC)
    by_id = {req.id: req for req in parsed.requirements}
    declarations = {
        req.id: req.observes_keys for req in parsed.requirements
    }
    assert any("user:cache:*" in keys for keys in declarations.values()), (
        f"the declaration was not lifted: {declarations}"
    )
    assert any("token:user:*" in keys for keys in declarations.values()), (
        f"the declaration was not lifted: {declarations}"
    )
    assert by_id  # the parse produced requirements


def test_a_requirement_without_a_declaration_gets_an_empty_list() -> None:
    parsed = parse_requirements("1. Something\nIt must behave.\n")
    assert parsed.requirements[0].observes_keys == []


def test_the_declaration_helper_reads_only_patterns() -> None:
    """A declaration that names no pattern is no declaration at all —
    not a pattern that matches nothing."""
    assert declared_key_patterns("observes keys: whatever") == []
    assert declared_key_patterns("observes keys: a:*, b:*") == ["a:*", "b:*"]
    assert declared_key_patterns("no declaration here") == []


# ── the compiler carries it ──────────────────────────────────────────────


def test_the_compiler_carries_the_declaration_into_the_candidate() -> None:
    parsed = parse_requirements(SPEC)
    candidates = compile_candidates(parsed.requirements)
    carried = [c.observes_keys for c in candidates if c.observes_keys]
    assert carried, "the candidates lost the declaration"
    assert any("user:cache:*" in keys for keys in carried)


# ── every compiled contract carries the field ────────────────────────────


def test_every_compiled_contract_carries_the_field() -> None:
    out = compile_contracts_node({  # type: ignore[arg-type]
        "requirement_text": SPEC,
        "use_llm": False,
        "job_id": "job-368",
    })
    contracts = out["contracts"]
    assert contracts
    for contract in contracts:
        assert "observes_keys" in contract
        assert isinstance(contract["observes_keys"], list)
    declared = [
        keys for contract in contracts for keys in contract["observes_keys"]
    ]
    assert any("user:cache:*" in keys for keys in declared), (
        "the compiled contracts lost the declaration"
    )


# ── the collector reads the FIELD, not the prose ──────────────────────────


def test_the_structured_field_is_enough_for_the_collector() -> None:
    """The point of the change: a contract that says nothing about the
    keys in prose, but carries them as a field, is still observed."""
    contract = {
        "id": "CACHE-01",
        "checker_type": "redis",
        "requirement": "the entry must be evicted on write",
        "observes_keys": ["user:cache:*"],
    }
    assert key_patterns_for(contract) == ["user:cache:*"]


def test_the_prose_declaration_still_works_for_old_contracts() -> None:
    """No migration window: the contracts that predate the field keep
    working, because the collector asks the spec language when the
    field is absent."""
    contract = {
        "id": "CACHE-01",
        "checker_type": "redis",
        "requirement": (
            "the cached user entry must be evicted on write\n"
            "observes keys: user:cache:*"
        ),
    }
    assert key_patterns_for(contract) == ["user:cache:*"]


def test_the_field_wins_over_the_prose() -> None:
    """The structured field is the authority: a contract that carries it
    is observed on THAT family, not on whatever its prose happens to
    mention."""
    contract = {
        "id": "CACHE-01",
        "checker_type": "redis",
        "requirement": (
            "the session token must be dropped\nobserves keys: token:user:*"
        ),
        "observes_keys": ["user:cache:*"],
    }
    assert key_patterns_for(contract) == ["user:cache:*"]


def test_a_contract_with_no_declaration_and_no_words_gets_nothing() -> None:
    """No declaration, no family, no observation — and no invention."""
    contract: dict[str, Any] = {
        "id": "TX-01",
        "checker_type": "sql",
        "requirement": "the order must be created",
    }
    assert key_patterns_for(contract) == []
