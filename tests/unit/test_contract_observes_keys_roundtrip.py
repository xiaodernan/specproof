"""The approved version keeps the key families it was approved with (#372).

Since #368 the key-family declaration is a STRUCTURED field of the spec
language, and the compiled contract carries it. The registry is where a
human approves a contract version — so the declaration has to travel
WITH the version: an approved contract that had to have its declaration
re-derived from today's spec would silently change what it is observed
against after the spec moved on.

These tests pin the shape of the column (JSON list, NULL for "declared
nothing") and the round-trip through the record.
"""

from __future__ import annotations

import json
from typing import Any

from agent.contracts.records import ContractRecord
from agent.contracts.storage import _observes_keys_json


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "test-CACHE-01",
        "version": 1,
        "checker_type": "redis",
        "requirement": "the cached entry must be evicted",
        "requirement_ref": "REQ-CACHE-01",
        "expected_behavior": "the cache key is gone after the write",
        "status": "APPROVED",
    }
    row.update(overrides)
    return row


def test_a_version_keeps_the_declaration_it_was_written_with() -> None:
    record = ContractRecord.from_row(
        _row(observes_keys=json.dumps(["user:cache:*"])),
    )
    assert record.observes_keys == ("user:cache:*",)
    assert record.to_dict()["observes_keys"] == ["user:cache:*"]
    assert record.to_candidate().observes_keys == ["user:cache:*"]


def test_the_declaration_survives_a_driver_that_hands_back_a_list() -> None:
    record = ContractRecord.from_row(_row(observes_keys=["user:cache:*"]))
    assert record.observes_keys == ("user:cache:*",)


def test_a_version_that_declared_nothing_declares_nothing() -> None:
    """NULL is a real state: "this version declared no key families" is
    different from "this version declared keys we lost"."""
    record = ContractRecord.from_row(_row(observes_keys=None))
    assert record.observes_keys == ()
    assert record.to_dict()["observes_keys"] == []


def test_an_unreadable_declaration_yields_nothing_rather_than_a_guess() -> None:
    record = ContractRecord.from_row(_row(observes_keys=17))
    assert record.observes_keys == ()


def test_the_column_holds_a_json_list_or_nothing() -> None:
    assert _observes_keys_json(["user:cache:*"]) == json.dumps(["user:cache:*"])
    assert _observes_keys_json([]) is None
    assert _observes_keys_json(None) is None
    assert _observes_keys_json("") is None
    # A JSON string that came from a driver is read, not stored twice.
    assert _observes_keys_json('["user:cache:*"]') == json.dumps(["user:cache:*"])


def test_the_declaration_is_not_a_change_detection_column() -> None:
    """The spec digest already covers "the spec changed" (a changed spec
    already creates a new version), so the declaration rides along with
    the version instead of being a second change detector."""
    from agent.contracts.storage import PERSISTED_CONTENT_COLUMNS

    assert "observes_keys" not in PERSISTED_CONTENT_COLUMNS


def test_the_approved_contracts_carry_the_declaration_into_the_pipeline(
    monkeypatch: Any,
) -> None:
    """The CLI's registry load is where the approved declaration reaches
    the contract dicts the pipeline runs on."""
    from agent.contracts.compiler import ContractCandidate
    from cli.specproof.commands import verify as verify_cmd

    candidate = ContractCandidate(
        id="test-CACHE-01",
        checker_type="redis",
        requirement="the cached entry must be evicted",
        requirement_ref="REQ-CACHE-01",
        expected_behavior="the cache key is gone after the write",
        observes_keys=["user:cache:*"],
        source="registry",
        approved=True,
        version=1,
    )

    class _Registry:
        def get_approved_for_repo(self, repo_path: str, digest: str) -> list[Any]:
            return [candidate]

    monkeypatch.setattr(
        "agent.contracts.registry.ContractRegistry", lambda *a, **k: _Registry(),
    )
    contracts = verify_cmd._load_approved_contracts(
        "/tmp/repo", "spec text", use_registry=True,
    )
    assert contracts
    assert contracts[0]["observes_keys"] == ["user:cache:*"]
