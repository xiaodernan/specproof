"""The Redis client is ONE per process, and its pool is BOUNDED (#1621).

Two separate facts, both load-bearing:

* **One client per process.** The worker builds several RedisStore
  instances (one per operation site), and every instance used to build
  its own client -- and therefore its own connection pool. The process
  then held one pool per store, each with its own TCP + AUTH handshake.
  One client per configuration means one pool and one handshake.
* **A bounded pool.** redis-py's default is "no bound": the pool grows
  with the concurrency, so "how many sockets does this process hold" was
  an open question. ``REDIS_MAX_CONNECTIONS`` turns it into a number.

The measurements are counts (how many connections the pool created, how
many pools exist), not timings: they do not wobble with the machine's
mood, and they are the properties themselves.

The legs that need a real Redis SKIP when none answers -- "cannot
measure" must not read as "measured clean".
"""

from __future__ import annotations

import os
from typing import Any

import pytest
import redis

import storage.redis as redis_module
from storage.redis import (
    REDIS_DEFAULT_MAX_CONNECTIONS,
    RedisConfig,
    RedisStore,
    close_shared_redis_clients,
    shared_redis_client,
)


def _config(**overrides: Any) -> RedisConfig:
    base = RedisConfig.from_env()
    fields = {
        "host": base.host,
        "port": base.port,
        "password": base.password,
        "db": base.db,
        "max_connections": 4,
    }
    fields.update(overrides)
    return RedisConfig(**fields)


def _redis_or_skip() -> RedisConfig:
    config = _config()
    try:
        client = shared_redis_client(config)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no reachable Redis for the pool legs: {exc}")
    return config


def _created(client: redis.Redis) -> int:
    return int(getattr(client.connection_pool, "_created_connections", 0))


def test_two_stores_with_the_same_config_share_one_client() -> None:
    """The pool belongs to the process, not to the store."""
    config = _config()
    first = RedisStore(config=config)
    second = RedisStore(config=config)
    assert first.client is second.client, (
        "the two stores built two clients -- the process holds two pools"
    )
    assert first.client.connection_pool is second.client.connection_pool


def test_a_different_configuration_gets_its_own_pool() -> None:
    """Sharing is per configuration, not global: two different Redis
    endpoints must not be handed the same client."""
    first = _config(max_connections=4)
    second = _config(max_connections=5)
    assert shared_redis_client(first) is not shared_redis_client(second)


def test_the_pool_is_bounded() -> None:
    """The bound is the configured one, and the knob is readable."""
    config = _config(max_connections=7)
    pool = shared_redis_client(config).connection_pool
    assert pool.max_connections == 7, (
        f"the pool's cap is {pool.max_connections}, not the configured 7"
    )
    assert RedisConfig.from_env().max_connections == int(
        os.getenv("REDIS_MAX_CONNECTIONS", REDIS_DEFAULT_MAX_CONNECTIONS)
    )


def test_the_pool_creates_one_connection_for_many_stores() -> None:
    """The measurable heart of the change.

    The OLD shape (one client per store) opens one connection per store
    that issues a command. The NEW shape (one client per process) opens
    one connection for all of them. The comparison is measured here, in
    the same test, so the claim is not "the new code looks better" but
    "the old shape really did cost N connections".
    """
    config = _redis_or_skip()
    shared = shared_redis_client(config)
    before = _created(shared)

    stores = [RedisStore(config=config) for _ in range(5)]
    for store in stores:
        store.client.set("specproof:test:pool:shared", "1")
    after_shared = _created(shared)

    assert after_shared - before <= 1, (
        f"five stores opened {after_shared - before} connections -- the pool "
        "is not shared"
    )

    # the old shape, for the comparison: a client per store
    old_clients = [
        redis.Redis(
            host=config.host,
            port=config.port,
            password=config.password,
            db=config.db,
            decode_responses=True,
        )
        for _ in range(5)
    ]
    before_old = sum(_created(c) for c in old_clients)
    for client in old_clients:
        client.set("specproof:test:pool:old", "1")
    after_old = sum(_created(c) for c in old_clients)
    for client in old_clients:
        client.close()

    assert after_old - before_old >= 5, (
        f"the old shape opened only {after_old - before_old} connections -- "
        "the comparison that makes the shared pool meaningful is not what "
        "it claims to be"
    )


def test_the_rate_limiter_path_does_not_open_a_connection_per_call() -> None:
    """The API's rate limiter builds a RedisStore per request.

    ``api/auth.py::enforce_rate_limit`` does ``store = RedisStore()`` on
    every call, so before #1621 every rate-limited request built a client,
    a pool, and a TCP + AUTH handshake of its own. The pattern is measured
    here exactly as the request path runs it.
    """
    config = RedisConfig.from_env()
    try:
        client = shared_redis_client(config)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no reachable Redis for the rate-limiter leg: {exc}")

    before = _created(client)
    for _ in range(5):
        RedisStore().client.incr("specproof:test:pool:rate-limit")
    after = _created(client)
    RedisStore().client.delete("specproof:test:pool:rate-limit")

    assert after - before <= 1, (
        f"five rate-limiter calls opened {after - before} connections -- the "
        "per-request store is still building a pool of its own"
    )


def test_closing_one_store_leaves_the_shared_client_usable() -> None:
    """close() releases the STORE's reference, not the process's socket.

    The worker's shutdown path closes a store that is not the only user
    of the pool; closing the shared client there would pull the socket
    out from under the other stores.
    """
    config = _redis_or_skip()
    first = RedisStore(config=config)
    second = RedisStore(config=config)
    first.client.set("specproof:test:pool:close", "1")
    first.close()
    assert second.client.get("specproof:test:pool:close") == "1", (
        "closing one store broke the shared client for the others"
    )
    second.client.delete("specproof:test:pool:close")


def test_closing_the_shared_clients_empties_the_registry() -> None:
    config = _redis_or_skip()
    shared_redis_client(config)
    close_shared_redis_clients()
    assert not redis_module._CLIENTS, (  # noqa: SLF001 - the registry is the point
        "the shared clients were closed but the registry still holds them"
    )
    # a fresh client is built on demand afterwards
    assert shared_redis_client(config) is not None
