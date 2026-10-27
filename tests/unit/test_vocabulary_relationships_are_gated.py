"""#480 — the vocabulary relationships that had no gate.

#475's observation: of five duplicated vocabularies, the four that had a
behavioural gate stayed correct, and the one without a gate drifted into a
security bug. A scan of module-level vocabulary declarations then found nine
that no test ever names.

This file gates the four that have a *checkable relationship* to another
vocabulary. The gates assert the relationship, not the literal list, so the
thing that turns them red is exactly the drift they exist to catch: a word
added on one side and not the other.

The remaining ungated declarations are left alone on purpose:
``evidence/lineage.py``'s ``NODE_KINDS``/``EDGE_TYPES`` are enforced at
runtime (an unknown word is rejected), and the rest have no partner
vocabulary to compare against.
"""
from __future__ import annotations

import pytest


def test_the_mcp_status_filter_is_the_contract_vocabulary_plus_all() -> None:
    """Two modules validate contract status; one uppercases, one lowercases.

    ``agent.contracts.records.CONTRACT_STATUSES`` is the registry's closed set
    (uppercase, enforced at construction). ``mcp.tools`` accepts a *filter*
    argument that is the same set lowercased plus ``"all"``. Adding a status
    to the registry without adding it here would make the MCP tool reject a
    filter for a status the product really has — the two are the same
    vocabulary, so the gate derives one from the other.
    """
    from agent.contracts.records import CONTRACT_STATUSES
    from mcp.tools import _ALLOWED_CONTRACT_STATUSES

    expected = {status.lower() for status in CONTRACT_STATUSES} | {"all"}
    assert expected == _ALLOWED_CONTRACT_STATUSES, (
        "mcp.tools' status filter drifted from the contract registry: "
        f"filter={sorted(_ALLOWED_CONTRACT_STATUSES)} expected={sorted(expected)}"
    )


def test_every_severe_level_is_a_declared_severity() -> None:
    """Inline comments render BLOCKER/MAJOR as "severe"; those words must exist.

    ``integrations.inline_comments._SEVERE_LEVELS`` is a subset of the policy
    DSL's severity vocabulary. A renamed or typo'd level here would silently
    stop a finding from being rendered as severe, so the subset relation is
    the contract.
    """
    from agent.policy_dsl import SEVERITIES
    from integrations.inline_comments import _SEVERE_LEVELS

    unknown = set(_SEVERE_LEVELS) - set(SEVERITIES)
    assert not unknown, (
        f"inline_comments treats {sorted(unknown)} as severe, but the policy "
        f"DSL declares only {sorted(SEVERITIES)}"
    )


def test_every_retired_status_is_a_real_job_status() -> None:
    """A retired status that no longer exists would never be swept.

    ``storage.mysql.RETIRED_STATUSES`` names the statuses the expiry reaper
    may retire. Every one of them must be a status the state machine actually
    has, or the reaper is waiting for a word nothing writes.
    """
    from storage.mysql import _VALID_TRANSITIONS, RETIRED_STATUSES

    unknown = set(RETIRED_STATUSES) - set(_VALID_TRANSITIONS)
    assert not unknown, (
        f"RETIRED_STATUSES names {sorted(unknown)}, which is not a job status; "
        f"the state machine has {sorted(_VALID_TRANSITIONS)}"
    )


def test_the_two_python_definition_kind_tuples_still_agree() -> None:
    """``craft.structured_diff`` declares the same kind set twice, 3 lines apart.

    One decides which symbols a definition contributes, the other which kinds
    may pair as a rename. They are equal today. If they must diverge, change
    this gate deliberately rather than letting one list drift away from the
    other by accident.
    """
    from craft.structured_diff import _DEF_KINDS, _RENAMABLE_KINDS

    assert _DEF_KINDS == _RENAMABLE_KINDS, (
        "structured_diff's two definition-kind tuples drifted: "
        f"_DEF_KINDS={_DEF_KINDS} _RENAMABLE_KINDS={_RENAMABLE_KINDS}"
    )


@pytest.mark.parametrize(
    "status", ["APPROVED", "PROPOSED", "REJECTED", "REVOKED"]
)
def test_the_mcp_filter_accepts_every_contract_status(status: str) -> None:
    """Behavioural counterpart: each real status has a lowercase filter form."""
    from mcp.tools import _ALLOWED_CONTRACT_STATUSES

    assert status.lower() in _ALLOWED_CONTRACT_STATUSES
