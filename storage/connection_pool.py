"""A bounded pool of database connections, shared per process (#1622).

WHY A POOL. The store used to open a connection per unit of work: every
query paid a TCP handshake and an authentication round trip, and the
process's connection count was whatever the concurrency happened to be --
unbounded from the application's point of view, and only the server's
``max_connections`` stood between the process and a refusal. A pool turns
both into numbers: the handshake is paid once and amortized, and the
number of connections this process holds is a cap the operator sets.

THE RULES THIS POOL FOLLOWS, and why each one is here:

* **A connection is reused only if it proves it is alive.** A pooled
  connection that the server dropped (MySQL's ``wait_timeout``, a
  restart, a NAT) fails on its first command with an error that names
  the query, not the network. The pool pings before handing a connection
  out, so a dead one is closed instead of served. A connection object
  that cannot be pinged is treated as dead -- "cannot prove it is
  alive" and "is alive" are not the same claim.
* **The pool is bounded, and exhaustion is an error, not a hang.** When
  every connection is in use and none comes back within the timeout, the
  acquire raises with the numbers in the message. Waiting forever would
  turn a saturated database into a stuck request with no story.
* **A connection belongs to ONE unit of work at a time.** The pool hands
  out exclusive leases: two threads never share a connection, so a
  transaction is never interleaved with another one's.
* **A connection is only reused by the same factory that made it.** The
  factory is the seam the tests use (they replace the store's connect
  method), and a connection made by one fake must never be handed to a
  test that is using another.

The pool is deliberately small and boring: it owns no policy about
transactions (that lives in ``storage/unit_of_work.py``), it never
silently swallows an error, and it reports what it is holding.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

#: How many connections ONE process may hold to the database.
#:
#: WHY A BOUND. Without a pool the process opened a connection per unit
#: of work, so the connection count was whatever the concurrency happened
#: to be -- the only ceiling was the server's ``max_connections``, and
#: reaching it looks like "the database is down". A pool makes the
#: ceiling the application's own decision (MYSQL_POOL_SIZE).
DEFAULT_POOL_SIZE = 8
#: How long a caller waits for a connection to come back before the pool
#: says so (seconds). Waiting forever would turn a saturated database
#: into a request with no story.
DEFAULT_ACQUIRE_TIMEOUT = 5.0


class Connection(Protocol):
    """The part of a DB-API connection the pool uses."""

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class PoolExhaustedError(RuntimeError):
    """The pool had no connection to give within its timeout.

    The message carries the numbers an operator needs: how many
    connections exist, how many are in use, and how long the caller
    waited.
    """

    def __init__(self, message: str, *, max_size: int, in_use: int, waited: float) -> None:
        super().__init__(message)
        self.max_size = max_size
        self.in_use = in_use
        self.waited = waited


@dataclass(frozen=True)
class PoolStats:
    """What the pool is holding right now."""

    #: Connections that exist (idle + in use).
    live: int
    #: Connections handed out right now.
    in_use: int
    #: Connections waiting to be handed out.
    idle: int
    #: The cap.
    max_size: int
    #: How many connections the pool has ever created (handshakes paid).
    created_total: int
    #: How many connections the pool has discarded after finding them dead.
    discarded_total: int
    #: How many acquires had to wait for a connection to come back.
    waits: int


class BoundedConnectionPool:
    """A small, bounded, process-wide pool of connections."""

    def __init__(
        self,
        *,
        max_size: int = 8,
        acquire_timeout: float = 5.0,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size 必须至少为 1")
        self._max_size = max_size
        self._acquire_timeout = acquire_timeout
        self._condition = threading.Condition()
        # (connection, factory) pairs: a connection is only reusable by the
        # factory that made it (see the module docstring).
        self._idle: list[tuple[Any, Callable[[], Any]]] = []
        self._live = 0
        self._in_use = 0
        self._created_total = 0
        self._discarded_total = 0
        self._waits = 0

    # ── the pool's own bookkeeping ────────────────────────────────────
    @property
    def max_size(self) -> int:
        return self._max_size

    def stats(self) -> PoolStats:
        with self._condition:
            return PoolStats(
                live=self._live,
                in_use=self._in_use,
                idle=len(self._idle),
                max_size=self._max_size,
                created_total=self._created_total,
                discarded_total=self._discarded_total,
                waits=self._waits,
            )

    # ── acquiring and releasing ───────────────────────────────────────
    def acquire(self, factory: Callable[[], Any]) -> Any:
        """Take a connection, creating one if the pool has room.

        ``factory`` is called only when a new connection is needed; it
        is the store's own connect method, which is the seam the tests
        replace.
        """
        with self._condition:
            deadline = time.monotonic() + self._acquire_timeout
            while True:
                conn = self._take_idle(factory)
                if conn is not None:
                    self._in_use += 1
                    return conn
                if self._live < self._max_size:
                    self._live += 1
                    try:
                        conn = factory()
                    except BaseException:
                        self._live -= 1
                        self._condition.notify()
                        raise
                    self._created_total += 1
                    self._in_use += 1
                    return conn
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolExhaustedError(
                        "no database connection became free within "
                        f"{self._acquire_timeout}s (max_size={self._max_size}, "
                        f"in_use={self._in_use})",
                        max_size=self._max_size,
                        in_use=self._in_use,
                        waited=self._acquire_timeout,
                    )
                self._waits += 1
                self._condition.wait(remaining)

    def release(self, conn: Any, factory: Callable[[], Any]) -> None:
        """Give a connection back; a dead one is closed instead."""
        with self._condition:
            self._in_use -= 1
            if _is_alive(conn):
                self._idle.append((conn, _factory_identity(factory)))
            else:
                self._live -= 1
                self._discarded_total += 1
                _close(conn)
            self._condition.notify()

    def close(self) -> None:
        """Close every idle connection (the in-use ones close on release)."""
        with self._condition:
            idle, self._idle = self._idle, []
            for conn, _factory in idle:
                self._live -= 1
                _close(conn)
            self._condition.notify()

    # ── internals ─────────────────────────────────────────────────────
    def _take_idle(self, factory: Callable[[], Any]) -> Any:
        """The first idle connection made by THIS factory that is still alive.

        "This factory" means the FUNCTION behind it: two store instances
        of the same class share one function, so the connection one of
        them opened is good for the other -- that is what pooling is for.
        The test seam replaces the class attribute, which is a different
        function, so a faked store still gets a pool of its own.
        """
        wanted = _factory_identity(factory)
        for index, (conn, made_by) in enumerate(self._idle):
            if made_by is not wanted:
                continue
            del self._idle[index]
            if _is_alive(conn):
                return conn
            # dead: close it and keep looking
            self._live -= 1
            self._discarded_total += 1
            _close(conn)
        return None


def _factory_identity(connect: Callable[[], Any]) -> Any:
    """The function behind a connect callable.

    A bound method belongs to the class it was defined on, so every
    store instance of that class shares one identity -- which is what
    lets the pool hand a connection made by one instance to another.
    """
    return getattr(connect, "__func__", connect)


def _is_alive(conn: Any) -> bool:
    """Is this connection still usable?

    A connection that cannot answer a ping cannot be proven alive, and an
    unproven connection is not one to hand out.
    """
    ping = getattr(conn, "ping", None)
    if not callable(ping):
        return False
    try:
        ping(reconnect=False)
    except Exception:  # noqa: BLE001 - a dead socket answers in every way
        return False
    return True


def _close(conn: Any) -> None:
    try:
        conn.close()
    except Exception as exc:  # noqa: BLE001 - teardown never replaces the cause
        logger.warning("pooled connection close failed: %s", exc)


#: The pools this process owns, keyed by what they connect to.
_POOLS: dict[tuple[Any, ...], BoundedConnectionPool] = {}


def pool_key(connect: Callable[[], Any], target: object | None = None) -> tuple[Any, ...]:
    """The identity of the pool a connect implementation belongs to.

    Two stores that talk to the SAME server share one pool (one handshake,
    one bounded set of sockets); two that talk to different servers never
    do. ``target`` is whatever names the server -- a config object or the
    connect kwargs -- and it is hashed by VALUE, so the key carries no
    password in readable form.

    A store built without a target (the tests build one) falls back to the
    connect implementation alone: the pool is then per implementation,
    which is still a bounded pool.
    """
    func = getattr(connect, "__func__", connect)
    if isinstance(target, dict):
        parts = sorted((str(k), repr(v)) for k, v in target.items())
    elif target is None:
        parts = []
    else:
        fields = getattr(target, "__dict__", None) or {}
        parts = sorted((str(k), repr(v)) for k, v in fields.items())
    digest = hashlib.sha256(repr(parts).encode("utf-8")).hexdigest()[:16]
    return (id(func), digest)


def pool_for(
    connect: Callable[[], Any], target: object | None = None
) -> BoundedConnectionPool:
    """The process's pool for this connect implementation and target."""
    key = pool_key(connect, target)
    pool = _POOLS.get(key)
    if pool is None:
        size = int(getattr(target, "pool_size", DEFAULT_POOL_SIZE) or DEFAULT_POOL_SIZE)
        timeout = float(
            getattr(target, "pool_acquire_timeout", DEFAULT_ACQUIRE_TIMEOUT)
            or DEFAULT_ACQUIRE_TIMEOUT
        )
        pool = BoundedConnectionPool(max_size=size, acquire_timeout=timeout)
        _POOLS[key] = pool
    return pool


def close_shared_connections() -> None:
    """Close every shared pool's idle connections (process teardown; tests)."""
    for pool in list(_POOLS.values()):
        pool.close()
    _POOLS.clear()


__all__ = [
    "BoundedConnectionPool",
    "DEFAULT_ACQUIRE_TIMEOUT",
    "DEFAULT_POOL_SIZE",
    "PoolExhaustedError",
    "PoolStats",
    "close_shared_connections",
    "pool_for",
    "pool_key",
]
