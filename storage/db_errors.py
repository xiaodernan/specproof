"""Recognising a duplicate-key failure without importing a driver.

MySQL reports ``ER_DUP_ENTRY`` as ``1062`` in ``args[0]``; SQLite reports
``"UNIQUE constraint failed"`` in the ``args[0]`` text. Two backends of two
different stores needed this same guess (#495), and a store that got it wrong
would turn an idempotent retry into a hard failure — or worse, swallow a
genuine error as "already there".

Deliberately string/int matching rather than ``except MySQLdb.IntegrityError``:
importing a driver to classify an exception the caller already caught would
make this module depend on whichever backend happens to be installed.
"""
from __future__ import annotations


def is_duplicate_key(exc: Exception) -> bool:
    """True when *exc* is a duplicate-key violation from MySQL or SQLite.

    Anything else is NOT classified here — the caller re-raises it, so a wrong
    ``True`` would hide a real error.
    """
    first = exc.args[0] if exc.args else ""
    if first == 1062:
        return True
    text = str(first)
    return "UNIQUE constraint failed" in text or "Duplicate entry" in text


__all__ = ["is_duplicate_key"]
