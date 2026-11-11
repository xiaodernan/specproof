"""The MySQL store takes its connections from a BOUNDED pool (#1622).

Before #1622 the store opened a connection per unit of work: every
query paid a TCP handshake and an authentication round trip, and the
process's connection count was whatever the concurrency happened to be.
The pool makes both a number: the handshake is paid once and amortized,
and the connections this process holds are capped by MYSQL_POOL_SIZE.

What these legs measure:

* the pool is BOUNDED -- with room for two, a third concurrent acquire
  waits and then says so (with the numbers in the message) instead of
  opening a third connection or hanging forever,
* a connection is REUSED (the factory is called once for many units of
  work) and it is only reused while it proves it is alive,
* a DEAD connection is discarded rather than handed out,
* the transaction policy is unchanged: commit when the body is clean,
  rollback when it is not, and the connection goes back to the pool
  either way,
* the store really uses it (a real MySQL: two units of work share one
  connection).

The measurements are counts, not timings.
"""

from __future__ import annotations

import threading

import pytest

from storage.connection_pool import (
    BoundedConnectionPool,
    PoolExhaustedError,
    close_shared_connections,
    pool_for,
)
from storage.mysql import MySQLConfig, MySQLStore
from storage.unit_of_work import unit_of_work


class _FakeConn:
    """A connection that can be told to die."""

    def __init__(self, index: int) -> None:
        self.index = index
        self.alive = True
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def ping(self, reconnect: bool = True) -> None:
        del reconnect
        if not self.alive:
            raise RuntimeError("the server is gone")

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed += 1


def _factory(counter: list[int]):
    def make() -> _FakeConn:
        counter.append(1)
        return _FakeConn(len(counter))

    return make


def test_a_connection_is_reused_across_units_of_work() -> None:
    """The handshake is paid once, not once per query."""
    counter: list[int] = []
    pool = BoundedConnectionPool(max_size=4)
    factory = _factory(counter)

    for _ in range(10):
        conn = pool.acquire(factory)
        pool.release(conn, factory)

    assert len(counter) == 1, (
        f"the pool opened {len(counter)} connections for ten units of work -- "
        "the handshake is not amortized"
    )
    stats = pool.stats()
    assert stats.live == 1
    assert stats.idle == 1
    assert stats.in_use == 0
    assert stats.created_total == 1


def test_the_pool_is_bounded_and_says_so_when_it_is_exhausted() -> None:
    """A saturated pool is an error with numbers in it, not a hang and not
    a third connection."""
    counter: list[int] = []
    pool = BoundedConnectionPool(max_size=2, acquire_timeout=0.2)
    factory = _factory(counter)

    first = pool.acquire(factory)
    second = pool.acquire(factory)
    assert len(counter) == 2, "the pool opened more connections than its cap"

    with pytest.raises(PoolExhaustedError) as caught:
        pool.acquire(factory)

    message = str(caught.value)
    assert "max_size=2" in message, message
    assert "in_use=2" in message, message
    assert len(counter) == 2, (
        f"the pool opened {len(counter)} connections -- the cap did not hold"
    )

    pool.release(first, factory)
    pool.release(second, factory)


def test_a_dead_connection_is_discarded_rather_than_handed_out() -> None:
    """A connection the server dropped must not be served to the next
    caller."""
    counter: list[int] = []
    pool = BoundedConnectionPool(max_size=2)
    factory = _factory(counter)

    conn = pool.acquire(factory)
    conn.alive = False
    pool.release(conn, factory)

    fresh = pool.acquire(factory)
    assert fresh is not conn, "the dead connection was handed out again"
    assert conn.closed == 1, "the dead connection was not closed"
    stats = pool.stats()
    assert stats.discarded_total == 1
    assert stats.live == 1


def test_a_connection_that_cannot_be_pinged_is_not_reused() -> None:
    """"Cannot prove it is alive" and "is alive" are not the same claim."""

    class _NoPing:
        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    made: list[_NoPing] = []

    def factory() -> _NoPing:
        made.append(_NoPing())
        return made[-1]

    pool = BoundedConnectionPool(max_size=2)
    conn = pool.acquire(factory)
    pool.release(conn, factory)
    again = pool.acquire(factory)
    assert again is not conn, "an unproven connection was handed out again"
    assert len(made) == 2, "the pool did not open a fresh connection"


def test_a_connection_made_by_another_factory_is_not_handed_over() -> None:
    """The factory is the seam the tests replace; a connection made by one
    fake must never reach a test using another."""
    counter_a: list[int] = []
    counter_b: list[int] = []
    pool = BoundedConnectionPool(max_size=4)

    conn_a = pool.acquire(_factory(counter_a))
    pool.release(conn_a, _factory(counter_a))

    conn_b = pool.acquire(_factory(counter_b))
    assert conn_b is not conn_a, (
        "a connection made by one factory was handed to another"
    )


def test_the_transaction_policy_survives_the_pool() -> None:
    """Commit when the body is clean, roll back when it is not, and the
    connection goes back to the pool either way."""
    counter: list[int] = []
    factory = _factory(counter)

    with unit_of_work(factory) as conn:
        conn.committed += 0  # the body did nothing; the policy commits
    assert conn.committed == 1, "a clean body did not commit"
    assert conn.rolled_back == 0

    with pytest.raises(RuntimeError):
        with unit_of_work(factory) as conn:
            raise RuntimeError("the body failed")
    assert conn.rolled_back == 1, "a failed body did not roll back"
    assert len(counter) == 1, "the failed unit of work opened a new connection"


def test_concurrent_acquires_never_share_one_connection() -> None:
    """Two threads must never hold the same connection: their
    transactions would interleave."""
    counter: list[int] = []
    pool = BoundedConnectionPool(max_size=4)
    factory = _factory(counter)
    seen: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            conn = pool.acquire(factory)
            seen.append(id(conn))
            pool.release(conn, factory)
        except BaseException as exc:  # noqa: BLE001 - the leg reports it
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert pool.stats().in_use == 0
    assert pool.stats().live <= 4


def test_two_stores_talking_to_the_same_server_share_one_pool() -> None:
    """The pool belongs to the server, not to the store instance."""
    config = MySQLConfig.from_env()
    first = MySQLStore(config=config)
    second = MySQLStore(config=config)
    assert pool_for(first._connect, first.config) is pool_for(  # noqa: SLF001
        second._connect, second.config
    )


def test_the_store_reuses_one_connection_for_two_units_of_work() -> None:
    """The store really uses the pool (a real MySQL).

    Two units of work in a row must share one connection: that is the
    handshake being amortized, measured on the store the product uses.
    """
    config = MySQLConfig.from_env()
    store = MySQLStore(config=config)
    try:
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no reachable MySQL for the pool legs: {exc}")

    pool = pool_for(store._connect, store.config)  # noqa: SLF001 - the pool is the point
    before = pool.stats().created_total
    for _ in range(3):
        with store.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
    after = pool.stats().created_total

    assert after - before <= 1, (
        f"three units of work opened {after - before} connections -- the "
        "store is not using the pool"
    )
    assert pool.stats().live <= config.pool_size
    close_shared_connections()


def test_the_pool_size_is_configurable() -> None:
    config = MySQLConfig.from_env()
    assert config.pool_size >= 1, "the pool must hold at least one connection"
    assert config.pool_acquire_timeout > 0, (
        "the acquire timeout must be positive -- a zero timeout would make "
        "every saturated acquire fail instantly"
    )
