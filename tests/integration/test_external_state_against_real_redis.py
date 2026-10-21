"""End-to-end against a REAL Redis: two moments, two real snapshots.

The unit tests use a double. This one talks to the actual service the
pipeline will talk to, because the two things a double cannot show are:

- the client really connects (the env vars are right);
- the snapshot really changes when the world changes (a key set between
  the two moments is VISIBLE as a difference).

Run it against the compose Redis:

    python -m pytest tests/integration/test_external_state_against_real_redis.py
"""
from __future__ import annotations

import os
import uuid
from contextlib import suppress
from typing import Any

import pytest

from experiments.collectors import redis_fragment_from_snapshots
from experiments.external_state import (
    build_redis_client,
    capture_redis_state,
    redis_states_from_dicts,
)

REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


@pytest.fixture()
def redis() -> Any:
    client = build_redis_client()
    if client is None:
        pytest.skip(
            f"no Redis reachable at {REDIS_HOST}:{REDIS_PORT} — set REDIS_URL "
            "(the conftest strips REDIS_PASSWORD on purpose, so a URL is "
            "the way to carry the credential)"
        )
    yield client
    with suppress(Exception):
        client.close()


def test_the_client_really_connects(redis: Any) -> None:
    assert redis.ping() is True


def test_two_real_moments_show_a_real_difference(redis: Any) -> None:
    """A key set between the two moments is visible as a difference.

    This is the whole point of the two-moment design, measured against
    the real service: the first snapshot does not have the key, the
    second does, and the fragment says so.
    """
    key = f"specproof:two-moments:{uuid.uuid4().hex}"

    # Moment 1: the key does not exist.
    first = capture_redis_state(redis, [key])
    assert first[key]["present"] is False
    assert first[key]["value"] is None

    # The world changes.
    redis.set(key, "alice", ex=60)

    # Moment 2: it does.
    second = capture_redis_state(redis, [key])
    assert second[key]["present"] is True
    assert second[key]["value"] == "alice"
    assert second[key]["ttl_seconds"] is not None
    assert second[key]["ttl_seconds"] > 0

    try:
        fragment = redis_fragment_from_snapshots(
            "job-real-redis",
            redis_states_from_dicts({"redis": first}),
            redis_states_from_dicts({"redis": second}),
        )
        assert fragment.comparison["changed_count"] == 1
        assert fragment.comparison["changed"][0]["change"] == "appeared"
        assert fragment.status == "AMBIGUOUS"
    finally:
        redis.delete(key)


def test_a_key_that_does_not_exist_is_absent_not_empty(redis: Any) -> None:
    """A missing key is ABSENT — not "present with an empty value".

    The difference is exactly what "the token was invalidated" versus
    "the token was never there" turns on.
    """
    key = f"specproof:absent:{uuid.uuid4().hex}"
    snapshot = capture_redis_state(redis, [key])
    state = snapshot[key]
    assert state["present"] is False
    assert state["value"] is None
    assert state["ttl_seconds"] is None


def test_an_empty_value_is_present_with_an_empty_value(redis: Any) -> None:
    """A key that exists with an empty value is PRESENT.

    Reporting it as absent would be a lie: the key IS there, and the
    difference between "present and empty" and "absent" is the whole
    point of the collector.
    """
    key = f"specproof:empty:{uuid.uuid4().hex}"
    redis.set(key, "", ex=60)
    try:
        snapshot = capture_redis_state(redis, [key])
        state = snapshot[key]
        assert state["present"] is True
        assert state["value"] == ""
    finally:
        redis.delete(key)


def test_two_identical_moments_really_do_say_nothing_changed(redis: Any) -> None:
    """The unchanged case is measured too — not only the interesting one."""
    key = f"specproof:same:{uuid.uuid4().hex}"
    redis.set(key, "bob", ex=60)
    try:
        first = capture_redis_state(redis, [key])
        second = capture_redis_state(redis, [key])
        fragment = redis_fragment_from_snapshots(
            "job-real-redis",
            redis_states_from_dicts({"redis": first}),
            redis_states_from_dicts({"redis": second}),
        )
        assert fragment.comparison["changed_count"] == 0
        assert fragment.status == "COMPLIANT"
    finally:
        redis.delete(key)
