"""「没看」与「看了没有」必须分开说 (#369).

An unreachable store and an empty store used to travel as the SAME
empty map: the snapshot said nothing about whether the collector had
looked at all, so "the store was down" read like "the key family was
empty" — two very different facts, one shape.

Now the capture says whether it looked (``redis_observed`` /
``objects_observed``), the fragment carries that flag, and the matrix
row discloses the matching limit — so a reader can tell which of the
two happened.
"""

from __future__ import annotations

from typing import Any

from agent.external_observation import (
    LIMIT_NOT_OBSERVED,
    LIMIT_STORE_UNREACHABLE,
    observation_for,
    observation_limits,
    observation_status,
)
from experiments.external_state import capture_external_state

KEY = "user:cache:1"


class _FakeRedis:
    """A Redis double: one key, present."""

    def __init__(self) -> None:
        self.values = {KEY: "alice"}

    def get(self, name: str) -> Any:
        return self.values.get(name)

    def ttl(self, name: str) -> int:
        return 60 if name in self.values else -2

    def scan_iter(self, match: str | None = None, count: int | None = None) -> Any:
        return iter(self.values)


# ── the capture says whether it looked ────────────────────────────────────


def test_a_snapshot_says_whether_the_stores_were_reachable() -> None:
    snapshot = capture_external_state(
        redis_client=_FakeRedis(), object_store=None,
    )
    assert snapshot["redis_observed"] is True
    assert snapshot["objects_observed"] is False


def test_an_unreachable_store_is_recorded_as_not_looked_at() -> None:
    """The empty map alone would read as "we looked and there was
    nothing"."""
    snapshot = capture_external_state(redis_client=None, object_store=None)
    assert snapshot["redis"] == {}
    assert snapshot["redis_observed"] is False
    assert snapshot["objects_observed"] is False


def test_the_differential_says_so_when_the_collector_is_unavailable(
    monkeypatch: Any,
) -> None:
    """The collector could not even be imported: that is a fact about
    the pipeline, and the snapshot says it (#369)."""
    import sys

    from agent.nodes import run_differential

    # A None entry in sys.modules makes the import fail the way a
    # missing dependency would.
    monkeypatch.setitem(sys.modules, "experiments.external_state", None)
    snapshot = run_differential._capture_external_state({})
    assert snapshot["redis_observed"] is False
    assert snapshot["objects_observed"] is False
    assert snapshot["note"] == "collector unavailable"


# ── the fragment carries the flag ─────────────────────────────────────────


def _state(*, store_reachable: bool, present: bool) -> dict[str, Any]:
    moment = {
        "redis": {
            KEY: {
                "key": KEY,
                "present": present,
                "value": "alice" if present else None,
                "ttl_seconds": 60 if present else None,
            },
        },
        "objects": {},
        "redis_observed": store_reachable,
    }
    return {
        "job_id": "job-369-0001",
        "contracts": [{
            "id": "CACHE-01",
            "checker_type": "redis",
            "requirement": (
                "the cached user entry must be evicted on write\n"
                "observes keys: user:cache:*"
            ),
        }],
        "external_state_base": moment,
        "external_state_head": moment,
    }


def test_the_fragment_carries_whether_the_store_was_reachable() -> None:
    observation = observation_for(
        _state(store_reachable=False, present=False), _state(
            store_reachable=False, present=False,
        )["contracts"][0],
    )
    assert observation is not None
    assert observation.extension["store_reachable"] is False


# ── the row discloses the right limit ─────────────────────────────────────


def _limits(store_reachable: bool, present: bool) -> list[str]:
    state = _state(store_reachable=store_reachable, present=present)
    observation = observation_for(state, state["contracts"][0])
    assert observation is not None
    assert observation_status(observation) == "NO_EVIDENCE"
    return observation_limits(observation)


def test_an_unreachable_store_is_disclosed_as_not_looked_at() -> None:
    limits = _limits(store_reachable=False, present=False)
    assert LIMIT_STORE_UNREACHABLE in limits
    assert LIMIT_NOT_OBSERVED not in limits


def test_an_empty_family_is_disclosed_as_looked_at() -> None:
    """The store answered; the family was empty. A different fact, and it
    says so."""
    limits = _limits(store_reachable=True, present=False)
    assert LIMIT_NOT_OBSERVED in limits
    assert LIMIT_STORE_UNREACHABLE not in limits
