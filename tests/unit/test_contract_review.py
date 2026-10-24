"""Tests for contract_review node — honest production writer for CONTRACT_REVIEW."""

import pytest

from agent.nodes.contract_review import (
    _has_unapproved_contracts,
    _unapproved_summary,
    contract_review_node,
)
from agent.state import Phase0State


def test_has_unapproved_contracts_false_when_all_approved() -> None:
    contracts = [
        {"id": "AUTH-01", "approved": True, "checker_type": "http"},
        {"id": "UNIQUE-01", "approved": True, "checker_type": "sql"},
    ]
    assert _has_unapproved_contracts(contracts) is False


def test_has_unapproved_contracts_true_when_any_unapproved() -> None:
    contracts = [
        {"id": "AUTH-01", "approved": True, "checker_type": "http"},
        {"id": "UNIQUE-01", "approved": False, "checker_type": "sql"},
    ]
    assert _has_unapproved_contracts(contracts) is True


def test_has_unapproved_contracts_false_when_empty() -> None:
    assert _has_unapproved_contracts([]) is False


def test_unapproved_summary_only_includes_unapproved() -> None:
    contracts = [
        {"id": "AUTH-01", "approved": True, "checker_type": "http", "requirement": "auth req"},
        {"id": "UNIQUE-01", "approved": False, "checker_type": "sql", "requirement": "unique req"},
        {"id": "TOKEN-01", "approved": False, "checker_type": "redis", "requirement": "token req"},
    ]
    summary = _unapproved_summary(contracts)
    assert len(summary) == 2
    assert {s["id"] for s in summary} == {"UNIQUE-01", "TOKEN-01"}


def test_contract_review_node_no_contracts() -> None:
    state: Phase0State = {
        "contracts": [],
        "errors": [],
        "requirement_text": "test",
    }
    result = contract_review_node(state)
    assert result["contract_review"]["status"] == "no_contracts"
    assert result["stage"] == "contract_review"
    # paused is only set when waiting for approval
    assert result.get("paused") is not True


def test_contract_review_node_all_approved() -> None:
    state: Phase0State = {
        "contracts": [
            {"id": "AUTH-01", "approved": True, "checker_type": "http"},
            {"id": "UNIQUE-01", "approved": True, "checker_type": "sql"},
        ],
        "errors": [],
        "requirement_text": "test",
    }
    result = contract_review_node(state)
    assert result["contract_review"]["status"] == "all_approved"
    assert result["stage"] == "contract_review"
    assert result.get("paused") is not True


def test_contract_review_node_waiting_for_approval() -> None:
    state: Phase0State = {
        "contracts": [
            {"id": "AUTH-01", "approved": True, "checker_type": "http"},
            {"id": "UNIQUE-01", "approved": False, "checker_type": "sql", "requirement": "unique req"},
        ],
        "errors": [],
        "requirement_text": "test",
    }
    result = contract_review_node(state)
    assert result["contract_review"]["status"] == "waiting_for_approval"
    assert result["stage"] == "contract_review"
    assert result["paused"] is True
    assert len(result["contract_review"]["unapproved"]) == 1
    assert result["contract_review"]["unapproved"][0]["id"] == "UNIQUE-01"


def test_contract_review_node_missing_approved_key_defaults_false() -> None:
    """Contracts without 'approved' key default to unapproved (safe default)."""
    state: Phase0State = {
        "contracts": [
            {"id": "AUTH-01", "checker_type": "http"},  # no approved key
        ],
        "errors": [],
        "requirement_text": "test",
    }
    result = contract_review_node(state)
    assert result["contract_review"]["status"] == "waiting_for_approval"
    assert result["paused"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])