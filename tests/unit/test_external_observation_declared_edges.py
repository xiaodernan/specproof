"""#481 — the observation module's documented asymmetries, pinned.

``test_external_observation.py`` already pins the main paths: nothing is
invented for a contract with no key family or a run with no two moments,
the disclosed limits are the collectors' facts, and the pack/row agree.

What it does not pin are the asymmetries the module's docstrings call
load-bearing:

* ``observation_decidable(None) is True`` — "there was no observation at
  all" is a DIFFERENT question from "the observation could not decide",
  and only the contract can tell them apart;
* a contract about a NON-store surface (http/sql/openapi) has nothing
  missing when there is no observation;
* a store contract WITH a key family and no observation is "we did not
  look" (not decidable), while one with NO key family is "nothing to
  look at" (decidable);
* one captured moment is not two: a run with only Base must produce no
  observation;
* the truncation list is de-duplicated across the two snapshots;
* an MQ observation whose extension omits ``both_sides_observed`` must
  not claim a one-sided report;
* ``observation_status(None)`` is the empty string, not a status word.

The module is unchanged by this file: these are behaviour pins.
"""
from __future__ import annotations

from typing import Any

from agent.external_observation import (
    LIMIT_MQ_BROKER_SIDE,
    LIMIT_MQ_ONE_SIDE,
    observation_decidable,
    observation_limits,
    observation_status,
    observations,
    observations_and_decidability,
)

KEY = "user:cache:1"


def _moment(*, present: bool, value: str = "alice") -> dict[str, Any]:
    return {
        "redis": {
            KEY: {
                "key": KEY,
                "present": present,
                "value": value if present else None,
                "ttl_seconds": 60 if present else None,
            },
        },
        "objects": {},
    }


def _contract(**overrides: Any) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "id": "CACHE-01",
        "checker_type": "redis",
        "requirement": "the entry must be evicted\nobserves keys: user:cache:*",
    }
    contract.update(overrides)
    return contract


def _state(
    *,
    base: dict[str, Any] | None = None,
    head: dict[str, Any] | None = None,
    contracts: list[Any] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "job_id": "job-481-0001",
        "contracts": contracts if contracts is not None else [_contract()],
    }
    if base is not None:
        state["external_state_base"] = base
    if head is not None:
        state["external_state_head"] = head
    return state


class _Obs:
    """Minimal stand-in for a fragment (``observation_limits`` uses getattr)."""

    def __init__(
        self,
        *,
        fragment_type: str = "redis",
        status: str = "NO_EVIDENCE",
        extension: dict[str, Any] | None = None,
    ) -> None:
        self.fragment_type = fragment_type
        self.status = status
        self.extension = extension or {}


# ── observation_decidable: None is not a failure ───────────────────────


def test_no_observation_at_all_is_decidable() -> None:
    # Documented asymmetry: None means "there was no observation", which is a
    # different question from "the observation could not decide". Only the
    # contract can tell those apart, so this function answers True.
    assert observation_decidable(None) is True


def test_an_unreachable_store_could_not_decide() -> None:
    assert observation_decidable(_Obs(extension={"store_reachable": False})) is False


def test_incomparable_moments_could_not_decide() -> None:
    assert observation_decidable(_Obs(extension={"moments_comparable": False})) is False


def test_absent_flags_default_to_decidable() -> None:
    # A snapshot that predates the flags is treated as "we looked".
    assert observation_decidable(_Obs(extension={})) is True


# ── The contract decides which "no observation" case it is ─────────────


def test_a_non_store_contract_with_no_observation_is_decidable() -> None:
    state = _state(
        contracts=[{"id": "HTTP-01", "checker_type": "http", "requirement": "returns 200"}]
    )
    _, decidable = observations_and_decidability(state)
    assert decidable["HTTP-01"] is True


def test_a_store_contract_with_a_key_family_and_no_observation_did_not_look() -> None:
    state = _state()  # no snapshots at all
    found, decidable = observations_and_decidability(state)
    assert found == {}
    assert decidable["CACHE-01"] is False


def test_a_store_contract_without_a_key_family_has_nothing_to_look_at() -> None:
    state = _state(contracts=[_contract(requirement="must not leak anything")])
    _, decidable = observations_and_decidability(state)
    assert decidable["CACHE-01"] is True


# ── One moment is not two ──────────────────────────────────────────────


def test_a_run_with_only_the_base_moment_produces_no_observation() -> None:
    state = _state(base=_moment(present=True), head=None)
    assert observations(state) == {}
    _, decidable = observations_and_decidability(state)
    assert decidable["CACHE-01"] is False


def test_a_run_with_only_the_head_moment_produces_no_observation() -> None:
    state = _state(base=None, head=_moment(present=True))
    assert observations(state) == {}


# ── Contract-list hygiene ──────────────────────────────────────────────


def test_non_mapping_and_blank_id_contracts_are_skipped() -> None:
    state = _state(
        base=_moment(present=True),
        head=_moment(present=False),
        contracts=["not a contract", {"id": "   ", "checker_type": "redis"}, _contract()],
    )
    found, decidable = observations_and_decidability(state)
    assert set(found) == {"CACHE-01"}
    assert set(decidable) == {"CACHE-01"}


# ── Truncation is de-duplicated across the two snapshots ───────────────


def test_the_truncated_list_is_deduplicated_across_snapshots() -> None:
    base = _moment(present=True)
    head = _moment(present=False)
    base["truncated_patterns"] = ["user:cache:*"]
    head["truncated_patterns"] = ["user:cache:*"]
    observation = observations(_state(base=base, head=head))["CACHE-01"]
    limits = observation_limits(observation)
    truncated = [text for text in limits if "观测被截断" in text]
    assert len(truncated) == 1, f"the same family was counted twice: {truncated}"
    # one family, not two: the count in the prose is the de-duplicated length.
    assert "1 个键族" in truncated[0]


# ── MQ extension defaults ──────────────────────────────────────────────


def test_an_mq_observation_without_the_both_sides_flag_claims_no_one_sidedness() -> None:
    # A fragment that predates `both_sides_observed` must not be reported as
    # a one-sided report; only the permanent broker-side limit applies.
    limits = observation_limits(
        _Obs(fragment_type="mq", extension={"observed_any_publish": True})
    )
    assert limits == [LIMIT_MQ_BROKER_SIDE]
    assert LIMIT_MQ_ONE_SIDE not in limits


def test_an_mq_observation_with_the_flag_off_discloses_one_sidedness() -> None:
    limits = observation_limits(
        _Obs(fragment_type="mq", extension={"both_sides_observed": False})
    )
    assert limits == [LIMIT_MQ_BROKER_SIDE, LIMIT_MQ_ONE_SIDE]


# ── Status accessor ────────────────────────────────────────────────────


def test_status_of_no_observation_is_the_empty_string() -> None:
    assert observation_status(None) == ""
    assert observation_status(_Obs(status="COMPLIANT")) == "COMPLIANT"
