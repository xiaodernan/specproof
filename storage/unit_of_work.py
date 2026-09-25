"""One shared MySQL unit of work for every store in this package.

Two decisions live here, and both exist because of a measured failure:

* One connection per unit of work: commit when the body finishes clean.
* Teardown never replaces the cause. ``rollback()`` and ``close()`` on a
  socket the server already dropped raise on their own
  (``pymysql.err.InterfaceError: (0, '')``). Letting that escape turns every
  lost-connection failure into a report about ROLLBACK, so the operator reads
  the wrong cause and debugs the wrong layer. A teardown failure is still a
  fact, so it is logged -- just never at the cost of the real exception.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from pymysql.connections import Connection

logger = logging.getLogger(__name__)


@contextmanager
def unit_of_work(connect: Callable[[], Connection]) -> Iterator[Connection]:
    """Run one transaction on a connection produced by ``connect``."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        _teardown(conn.rollback, "rollback", "after the failure above")
        raise
    finally:
        _teardown(conn.close, "close", "on top of the failure above")


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
