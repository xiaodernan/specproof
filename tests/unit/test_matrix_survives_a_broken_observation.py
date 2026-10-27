"""#502 — when the observation layer RAISES, the matrix must not certify.

``build_matrix`` says, in its own comment: "A failure to observe is never fatal
to the matrix: the matrix is the verdict layer, and an unreadable observation
must not become a verdict."

The code did not do that. On an exception it emptied
``observation_decidable_by_contract`` and then read every row with
``.get(contract_id, True)`` — so every contract defaulted to *decidable*, the
"we did not look" downgrade never fired, and a PASS on a contract about an
external surface survived as VERIFIED. The comment promised fail-closed; the
default was fail-open.

These tests pin the fail-closed behaviour, and the precision that goes with it:
a contract that names **no** external surface is not downgraded by an unrelated
failure, because for it nothing is missing.
"""
from __future__ import annotations

from typing import Any

import pytest

import agent.nodes.build_matrix as matrix_module
from evidence.verdict import ROW_REASON_EXTERNAL_NOT_OBSERVED

_REDIS_CONTRACT = {
    "id": "CACHE-01",
    "checker_type": "redis",
    "requirement": "the cached entry must be evicted\nobserves keys: user:cache:*",
}

_JAVA_CONTRACT = {
    "id": "AUTH-01",
    "checker_type": "java",
    "requirement": "unauthenticated requests must receive 401",
}


def _matrix_for(contract: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "contracts": [dict(contract)],
        "contract_results": [{
            "contract_id": contract["id"],
            "result": "PASS",
            "experiment": "EXP-1",
            "evidence_ref": f"static:{contract['id']}:abc",
        }],
    }
    return matrix_module.build_matrix_node(state)["matrix"]  # type: ignore[arg-type]


@pytest.fixture()
def broken_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(state: Any, contracts: Any = None) -> Any:
        raise RuntimeError("observation layer exploded")

    monkeypatch.setattr(matrix_module, "observations_and_decidability", boom)


def test_a_broken_observation_layer_cannot_certify_a_store_contract(
    broken_observation: None,
) -> None:
    matrix = _matrix_for(_REDIS_CONTRACT)
    row = matrix["rows"][0]

    assert row["observation_decidable"] is False
    assert row["result"] == "UNVERIFIED"
    assert row["unverified_reason_code"] == ROW_REASON_EXTERNAL_NOT_OBSERVED
    assert matrix["passed"] == 0


def test_a_broken_observation_layer_does_not_touch_a_contract_with_no_surface(
    broken_observation: None,
) -> None:
    # Nothing was missing for this contract: it never named an external
    # surface, so an unrelated failure must not refuse its PASS.
    matrix = _matrix_for(_JAVA_CONTRACT)
    row = matrix["rows"][0]

    assert row["observation_decidable"] is True
    assert row["result"] == "PASS"
    assert matrix["passed"] == 1


def test_the_happy_path_still_reads_the_computed_decidability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The flag must not change the normal path: the comparison's own answer wins.
    monkeypatch.setattr(
        matrix_module,
        "observations_and_decidability",
        lambda state, contracts=None: ({}, {"CACHE-01": False}),
    )
    matrix = _matrix_for(_REDIS_CONTRACT)
    assert matrix["rows"][0]["observation_decidable"] is False
