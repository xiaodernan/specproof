"""A PASS on a surface the run never looked at is not a PASS (#379).

The external observation was computed and carried on the matrix row
(#365), and the row disclosed what it could not say. But the VERDICT
layer did not read it: a contract about Redis whose store was never
reached still came back VERIFIED, and the reader had to know to look at
a disclosure field nobody quoted.

So the observation reaches the verdict now, through the row (the verdict
layer does no I/O of its own — the comparison is made once, outside, and
the row carries its outcome):

- a contract whose external surface was NOT observed cannot be backed by
  a PASS that says nothing about that surface: the row is UNVERIFIED and
  the verdict is NEEDS_REVIEW (a GAP — the evidence is missing, not the
  defect);
- a contract that names no external surface is untouched: there was
  nothing to look at, so nothing is missing;
- a row that does not carry the field is untouched: an older producer's
  row must not be read as a claim.
"""

from __future__ import annotations

from typing import Any

from agent.external_observation import (
    observations_and_decidability,
)
from agent.nodes.build_matrix import build_matrix_node
from evidence.verdict import (
    ROW_REASON_EXTERNAL_NOT_OBSERVED,
    evaluate_verification,
)

KEY = "user:cache:1"

_REDIS_CONTRACT = {
    "id": "CACHE-01",
    "checker_type": "redis",
    "requirement": (
        "the cached user entry must be evicted on write\n"
        "observes keys: user:cache:*"
    ),
}

#: The same contract WITHOUT a key family: it names no external surface,
#: so there is nothing to observe and nothing is missing.
_REDIS_CONTRACT_NO_KEYS = {
    "id": "CACHE-01",
    "checker_type": "redis",
    "requirement": "the response must carry the request id header",
}

_JAVA_CONTRACT = {
    "id": "AUTH-01",
    "checker_type": "java",
    "requirement": "unauthenticated requests must receive 401",
}


def _moment(*, reachable: bool, present: bool) -> dict[str, Any]:
    return {
        "redis": {
            KEY: {
                "key": KEY,
                "present": present,
                "value": "alice" if present else None,
                "ttl_seconds": 60 if present else None,
            },
        },
        "objects": {},
        "redis_observed": reachable,
    }


def _state(
    contract: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    head: dict[str, Any] | None = None,
    reset: bool = True,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "contracts": [dict(contract)],
        # The two moments are only comparable when the external world was
        # reset between them — otherwise the head's store may still be
        # carrying the base's keys.
        "external_reset": {"reset": reset},
    }
    if base is not None:
        state["external_state_base"] = base
    if head is not None:
        state["external_state_head"] = head
    return state


def _decidable(state: dict[str, Any]) -> bool:
    _observations, decidable = observations_and_decidability(state)
    return decidable["CACHE-01" if "CACHE-01" in decidable else "AUTH-01"]


# ── the comparison says whether it could decide ───────────────────────────


def test_a_contract_about_the_store_with_no_moments_is_not_decidable() -> None:
    """The two moments were never captured: the run did not LOOK."""
    state = _state(_REDIS_CONTRACT)
    assert _decidable(state) is False


def test_an_unreachable_store_is_not_decidable() -> None:
    """The store was down (#369): we did not look."""
    moment = _moment(reachable=False, present=False)
    state = _state(_REDIS_CONTRACT, base=moment, head=moment)
    assert _decidable(state) is False


def test_a_reachable_store_with_the_family_present_is_decidable() -> None:
    moment = _moment(reachable=True, present=True)
    state = _state(_REDIS_CONTRACT, base=moment, head=moment)
    assert _decidable(state) is True


def test_a_contract_that_names_no_key_family_has_nothing_to_look_at() -> None:
    """No key family: there was nothing to observe, so nothing is missing."""
    state = _state(_REDIS_CONTRACT_NO_KEYS)
    assert _decidable(state) is True


def test_a_contract_with_no_external_surface_is_decidable() -> None:
    state = _state(_JAVA_CONTRACT)
    assert _decidable(state) is True


# ── the row carries the outcome ───────────────────────────────────────────


def _matrix_for(contract: dict[str, Any], state_extra: dict[str, Any]) -> dict:
    state: dict[str, Any] = {
        "contracts": [dict(contract)],
        "contract_results": [{
            "contract_id": contract["id"],
            "result": "PASS",
            "experiment": "EXP-1",
            "evidence_ref": "static:CACHE-01:abc",
        }],
    }
    state.update(state_extra)
    out = build_matrix_node(state)  # type: ignore[arg-type]
    return out["matrix"]


def test_the_row_carries_whether_the_observation_could_decide() -> None:
    matrix = _matrix_for(_REDIS_CONTRACT, {})
    row = matrix["rows"][0]
    assert row["observation_decidable"] is False
    assert row["observation_status"] == "", (
        "there was no observation, and the row says so"
    )


def test_a_pass_on_an_unobserved_surface_does_not_survive_the_matrix() -> None:
    """The row itself must not say PASS about a surface nobody looked at."""
    matrix = _matrix_for(_REDIS_CONTRACT, {})
    row = matrix["rows"][0]
    assert row["result"] == "UNVERIFIED"
    assert row["unverified_reason_code"] == ROW_REASON_EXTERNAL_NOT_OBSERVED
    assert matrix["passed"] == 0
    assert matrix["unverified"] == 1


def test_a_pass_on_an_observed_surface_survives() -> None:
    moment = _moment(reachable=True, present=True)
    matrix = _matrix_for(
        _REDIS_CONTRACT,
        {
            "external_state_base": moment,
            "external_state_head": moment,
            "external_reset": {"reset": True},
        },
    )
    row = matrix["rows"][0]
    assert row["observation_decidable"] is True
    assert row["result"] == "PASS"
    assert matrix["passed"] == 1


def test_a_moment_pair_that_cannot_be_compared_is_not_decidable() -> None:
    """The world was not reset between the two moments: the head's store
    may still be carrying the base's keys, so the two cannot be compared
    and the observation cannot decide anything."""
    moment = _moment(reachable=True, present=True)
    state = _state(_REDIS_CONTRACT, base=moment, head=moment, reset=False)
    assert _decidable(state) is False


# ── the verdict layer reads the row ───────────────────────────────────────


def _row(**extra: Any) -> dict[str, Any]:
    row = {
        "contract_id": "CACHE-01",
        "result": "PASS",
        "evidence_refs": ["static:CACHE-01:abc"],
        "experiment_ids": ["EXP-1"],
    }
    row.update(extra)
    return row


def test_a_pass_on_an_unobserved_surface_is_not_accepted() -> None:
    decision = evaluate_verification(
        {"rows": [_row(observation_decidable=False)]},
    )
    assert decision.status == "NEEDS_REVIEW"
    assert decision.passed == 0
    assert decision.unverified == 1
    assert any("外部观测面未被观测" in reason for reason in decision.reasons)


def test_the_missing_observation_is_a_gap_not_a_block() -> None:
    """Nothing is proven wrong: the evidence is missing. A reader told
    BLOCKED goes hunting for a defect; a reader told NEEDS_REVIEW goes
    looking for the missing observation."""
    decision = evaluate_verification(
        {"rows": [_row(observation_decidable=False)]},
    )
    assert decision.blocking == ()
    assert decision.status == "NEEDS_REVIEW"


def test_a_row_without_the_field_is_untouched() -> None:
    """An older producer's row makes no claim about the observation, so
    the verdict must not read one into it."""
    decision = evaluate_verification({"rows": [_row()]})
    assert decision.status == "VERIFIED"
    assert decision.passed == 1
