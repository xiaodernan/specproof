"""One shared MySQL unit of work for every store in this package.

Three decisions live here, and each exists because of a measured failure:

* One connection per unit of work: commit when the body finishes clean.
* Teardown never replaces the cause. ``rollback()`` and ``close()`` on a
  socket the server already dropped raise on their own
  (``pymysql.err.InterfaceError: (0, '')``). Letting that escape turns every
  lost-connection failure into a report about ROLLBACK, so the operator reads
  the wrong cause and debugs the wrong layer. A teardown failure is still a
  fact, so it is logged -- just never at the cost of the real exception.
* The connection comes from a POOL (#1622). Every store used to open a
  connection per operation, so every query paid a TCP handshake and an
  authentication round trip, and the process's connection count was
  whatever the concurrency happened to be. One shared implementation that
  takes its connection from a bounded pool keeps the transaction policy in
  one place AND makes the number of connections this process holds a
  number an operator sets (MYSQL_POOL_SIZE).

  A pooled connection is RELEASED, not closed: closing it would throw
  away the handshake the pool exists to amortize. The pool closes a
  connection it cannot prove is alive (and a connection that cannot be
  pinged at all is closed -- "cannot prove it is alive" and "is alive"
  are not the same claim).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from pymysql.connections import Connection

from storage.connection_pool import pool_for

logger = logging.getLogger(__name__)


@contextmanager
def unit_of_work(connect: Callable[[], Connection]) -> Iterator[Connection]:
    """Run one transaction on a connection taken from the process's pool.

    The pool is keyed by the connect implementation AND by what it talks
    to: two stores that talk to the same server share one pool, and two
    that talk to different servers never do. The target is read from the
    store that owns the connect method (its config, or its connect
    kwargs), so the callers do not have to repeat it -- and a connect
    method that is not bound to a store (the tests build one) simply has
    no target, which leaves the pool keyed by the implementation alone.
    """
    pool = pool_for(connect, _target_of(connect))
    conn = pool.acquire(connect)
    try:
        yield conn
        conn.commit()
    except Exception:
        _teardown(conn.rollback, "rollback", "after the failure above")
        raise
    finally:
        pool.release(conn, connect)


def _target_of(connect: Callable[[], Connection]) -> Any | None:
    """What the connection talks to, read from the store that owns it."""
    owner = getattr(connect, "__self__", None)
    if owner is None:
        return None
    for attribute in ("config", "_connect_kwargs"):
        value = getattr(owner, attribute, None)
        if value is not None:
            return value
    return None


def _teardown(action: Callable[[], object], label: str, when: str) -> None:
    try:
        action()
    except Exception as exc:
        logger.warning(
            "mysql %s failed %s; the exception the caller sees is the real "
            "cause, this one only says the handle was already gone: %s",
            label,
            when,
            exc,
        )
