"""The external world observed at TWO moments — not one snapshot twice.

A differential run executes the same generated test against the Base
workspace and the Head workspace. Both talk to the SAME Redis / MinIO.
So the difference between "the world after the Base run" and "the world
after the Head run" is exactly the difference the Head code made — and
it is the only thing a base/head comparison can be about.

A snapshot taken once and compared with ITSELF says "nothing changed"
forever. It is honest and useless at the same time.

These tests pin:
- the collector compares the two moments the pipeline captured;
- a difference between the moments is reported as a change;
- a missing moment is NO_EVIDENCE, never a fabricated COMPLIANT;
- the capture helper records a store that could not be reached as
  "we did not look", not as "everything is absent".
"""

from __future__ import annotations

from typing import Any

import pytest

from experiments.collectors import (
    KeyState,
    ObjectState,
    object_fragment_from_snapshots,
    redis_fragment_from_snapshots,
)
from experiments.external_state import (
    capture_external_state,
    object_states_from_dicts,
    redis_states_from_dicts,
)

BUCKET = "specproof"
KEY = "user:cache:1"
REF = f"{BUCKET}/jobs/j-1/capsule.zip"


class _FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}

    def get(self, name: str) -> Any:
        return self.values.get(name)

    def ttl(self, name: str) -> int:
        return 60 if name in self.values else -2


class _FakeObjectStore:
    def __init__(self, objects: dict[str, dict[str, Any]] | None = None) -> None:
        self.objects = objects or {}

    def object_exists(self, bucket: str, object_name: str) -> bool:
        return f"{bucket}/{object_name}" in self.objects

    def object_stat(self, bucket: str, object_name: str) -> dict[str, Any]:
        return dict(self.objects[f"{bucket}/{object_name}"])


# ── the two moments ────────────────────────────────────────────────────────


def test_a_difference_between_the_two_moments_is_a_change() -> None:
    """The whole point: the Head run left the key behind, the Base did not."""
    base = {KEY: KeyState(key=KEY, present=False)}
    head = {KEY: KeyState(key=KEY, present=True, value="alice", ttl_seconds=60)}

    fragment = redis_fragment_from_snapshots("job-1", base, head)

    assert fragment.status == "AMBIGUOUS"
    assert fragment.comparison["changed_count"] == 1
    assert fragment.comparison["changed"][0]["change"] == "appeared"
    assert fragment.extension["observed_any_key"] is True


def test_two_identical_moments_say_nothing_changed() -> None:
    base = {KEY: KeyState(key=KEY, present=True, value="alice", ttl_seconds=60)}
    head = {KEY: KeyState(key=KEY, present=True, value="alice", ttl_seconds=60)}

    fragment = redis_fragment_from_snapshots("job-1", base, head)

    assert fragment.comparison["changed_count"] == 0
    assert fragment.status == "COMPLIANT"


def test_no_moment_observed_is_no_evidence() -> None:
    """An empty observation claims nothing — not even "it was fine"."""
    fragment = redis_fragment_from_snapshots("job-1", {}, {})

    assert fragment.status == "NO_EVIDENCE"
    assert fragment.confidence == 0.0
    assert fragment.extension["observed_any_key"] is False


def test_the_object_fragment_compares_two_moments_too() -> None:
    base = {REF: ObjectState(BUCKET, "jobs/j-1/capsule.zip", present=False)}
    head = {
        REF: ObjectState(
            BUCKET, "jobs/j-1/capsule.zip", present=True,
            size_bytes=42, content_type="application/zip", sha256="a" * 64,
        )
    }

    fragment = object_fragment_from_snapshots("job-1", base, head)

    assert fragment.status == "AMBIGUOUS"
    assert fragment.comparison["changed"][0]["change"] == "appeared"
    assert fragment.fragment_type == "object"


# ── the capture helper ──────────────────────────────────────────────────────


def test_the_capture_records_what_it_actually_saw() -> None:
    redis = _FakeRedis({KEY: "alice"})
    objects = _FakeObjectStore({
        REF: {"size_bytes": 42, "content_type": "application/zip", "sha256": "a" * 64}
    })

    snapshot = capture_external_state(
        redis_client=redis, object_store=objects,
        redis_keys=[KEY], object_refs=[REF],
    )

    assert snapshot["redis"][KEY]["present"] is True
    assert snapshot["redis"][KEY]["value"] == "alice"
    assert snapshot["objects"][REF]["present"] is True
    assert snapshot["objects"][REF]["size_bytes"] == 42


def test_an_unreachable_store_captures_nothing() -> None:
    """An empty capture means "we did not look".

    It must NOT look like "we looked and every key was absent" — that
    is what a capture with present=false entries says, and the two mean
    opposite things.
    """
    snapshot = capture_external_state(
        redis_client=None, object_store=None,
        redis_keys=[KEY], object_refs=[REF],
    )

    assert snapshot["redis"] == {}
    assert snapshot["objects"] == {}
    # And the rebuild yields NO states at all — not absent ones.
    assert redis_states_from_dicts(snapshot) == {}
    assert object_states_from_dicts(snapshot) == {}


def test_a_captured_snapshot_rebuilds_into_typed_states() -> None:
    redis = _FakeRedis({KEY: "alice"})
    snapshot = capture_external_state(
        redis_client=redis, object_store=None, redis_keys=[KEY],
    )

    states = redis_states_from_dicts(snapshot)

    assert KEY in states
    assert states[KEY].present is True
    assert states[KEY].value == "alice"
    assert states[KEY].ttl_seconds == 60


def test_a_snapshot_survives_the_trip_through_plain_dicts() -> None:
    """The snapshot travels through the pipeline state as plain JSON."""
    import json

    redis = _FakeRedis({KEY: "alice"})
    snapshot = capture_external_state(
        redis_client=redis, object_store=None, redis_keys=[KEY],
    )

    round_tripped = json.loads(json.dumps(snapshot))

    assert round_tripped == snapshot
    states = redis_states_from_dicts(round_tripped)
    assert states[KEY].present is True


@pytest.mark.parametrize("missing", [None, {}])
def test_a_missing_snapshot_yields_no_states(missing: Any) -> None:
    assert redis_states_from_dicts(missing) == {}
    assert object_states_from_dicts(missing) == {}
