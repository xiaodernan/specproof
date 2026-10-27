"""The one parser for the MySQL URL every store reads.

Four stores — ``agent_jobs``, ``billing``, ``identity``, ``object_metadata`` —
each carried a byte-identical copy of this function (#484). Connection-string
parsing is the wrong place for four implementations: a fix to the scheme
check, the default port or the default database would reach one store and
not the other three, and every store would still look self-consistent.

Kept in its own module rather than folded into ``storage/mysql.py`` so the
four stores do not gain a dependency on the whole MySQL client module for
one pure function.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlsplit

from pymysql.cursors import DictCursor


def parse_mysql_url(url: str) -> dict[str, Any]:
    """Turn a ``mysql://`` URL into PyMySQL connection kwargs.

    Accepts ``mysql://`` and ``mysql+pymysql://`` (the SQLAlchemy spelling the
    deployment files use). A missing path means the default database; a
    missing port means 3306. Credentials are percent-decoded, because a
    password with ``@`` or ``:`` in it must survive the URL.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError(f"expected a mysql:// URL, got scheme {parsed.scheme!r}")
    if parsed.hostname is None:
        raise ValueError("MySQL URL must include a host")
    database = (parsed.path or "/").lstrip("/")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username is not None else "",
        "password": unquote(parsed.password) if parsed.password is not None else "",
        "database": database or "specproof",
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


__all__ = ["parse_mysql_url"]
