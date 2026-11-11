"""The worker lease, measured against a REAL Redis (#1611).

Why this file exists beside the logic test (``test_lease_max_hold.py``):
that one answers "what do the lease rules say" against a dict; this one
answers "does the server behave that way" — the properties that only a real
Redis can show are:

* **the acquisition is atomic** — the lease and both max-hold markers exist
  the moment ``acquire_lease`` returns (the old shape wrote the markers in
  two follow-up round trips, so a crash in between left a lease with no cap,
  and a lease with no cap is renewed forever);
* **the renewal is atomic** — a non-owner's renewal returns False AND does
  not extend the owner's TTL (the old shape read the owner first and
  extended last, so a lease that changed hands in between was still
  extended by the previous owner);
* **one round trip** — the renewal issues exactly one command (EVAL), not
  the four it used to (GET / EXISTS / EXISTS / EXPIRE);
* **contention has exactly one winner** — eight threads racing for the
  same lease: one acquires, seven are refused.

The file skips (with the reason) when no Redis answers: the CI leg that
runs the unit suite has no Redis, and "cannot measure" must not be reported
as "measured clean". On a machine with Redis (the dev box, the observability
stack) every leg runs for real.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest

from storage.redis import RedisStore


def _store() -> RedisStore:
    store = RedisStore()
    try:
        store.client.ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "no Redis here"
        pytest.skip(f"no reachable Redis for the lease legs: {type(exc).__name__}: {exc}")
    return store


def _job_id() -> str:
    return f"lease-atomicity-{uuid.uuid4().hex[:12]}"


def _cleanup(store: RedisStore, job_id: str) -> None:
    client = store.client
    for key in (
        store.lease_key(job_id),
        store.lease_start_key(job_id),
        store.lease_cap_flag_key(job_id),
    ):
        client.delete(key)


def test_the_cap_markers_exist_the_moment_the_lease_does() -> None:
    store = _store()
    job_id = _job_id()
    try:
        assert store.acquire_lease(job_id, "w1", ttl=30, max_hold_seconds=300) is True
        assert store.client.get(store.lease_key(job_id)) == "w1"
        assert store.client.exists(store.lease_cap_flag_key(job_id)) == 1
        assert store.client.exists(store.lease_start_key(job_id)) == 1
    finally:
        _cleanup(store, job_id)


def test_a_non_owner_cannot_renew_and_cannot_extend_the_owners_ttl() -> None:
    store = _store()
    job_id = _job_id()
    try:
        assert store.acquire_lease(job_id, "w1", ttl=30, max_hold_seconds=300)
        ttl_before = store.client.ttl(store.lease_key(job_id))
        assert store.renew_lease(job_id, "w2", ttl=30) is False
        ttl_after = store.client.ttl(store.lease_key(job_id))
        assert ttl_after == ttl_before, (
            f"a refused renewal still moved the TTL ({ttl_before} -> {ttl_after}); "
            "the ownership check and the extension have to be one step"
        )
    finally:
        _cleanup(store, job_id)


def test_the_renewal_costs_exactly_one_round_trip() -> None:
    store = _store()
    job_id = _job_id()
    calls: list[str] = []
    inner = store.client

    class _Counting:
        """Counts the commands the store issues (the round trips it pays)."""

        def __getattr__(self, name):
            attr = getattr(inner, name)
            if not callable(attr):
                return attr

            def wrapper(*args, **kwargs):
                calls.append(name)
                return attr(*args, **kwargs)

            return wrapper

    try:
        assert store.acquire_lease(job_id, "w1", ttl=30, max_hold_seconds=300)
        store._client = _Counting()
        calls.clear()
        assert store.renew_lease(job_id, "w1", ttl=30) is True
        assert calls == ["eval"], (
            f"the renewal issued {calls}; one EVAL is the whole point of the "
            "atomic shape (it used to be GET + EXISTS + EXISTS + EXPIRE)"
        )
    finally:
        store._client = inner
        _cleanup(store, job_id)


def test_eight_racers_produce_exactly_one_winner() -> None:
    store = _store()
    job_id = _job_id()
    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def _race(worker: str) -> None:
        barrier.wait()
        won = store.acquire_lease(job_id, worker, ttl=30, max_hold_seconds=300)
        with lock:
            results.append(won)

    threads = [threading.Thread(target=_race, args=(f"w{i}",)) for i in range(8)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert len(results) == 8
        assert sum(1 for won in results if won) == 1, (
            f"{sum(1 for won in results if won)} of 8 racers acquired the same lease; "
            "SET NX is the only thing making that impossible"
        )
        owner = store.get_lease_owner(job_id)
        assert owner is not None
    finally:
        _cleanup(store, job_id)


def test_the_max_hold_window_still_refuses_a_renewal_after_it_lapses() -> None:
    store = _store()
    job_id = _job_id()
    try:
        assert store.acquire_lease(job_id, "w1", ttl=30, max_hold_seconds=1)
        assert store.renew_lease(job_id, "w1", ttl=30) is True
        time.sleep(1.3)  # the start marker (the max-hold window) expires
        assert store.renew_lease(job_id, "w1", ttl=30) is False
    finally:
        _cleanup(store, job_id)
