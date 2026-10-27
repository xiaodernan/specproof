"""#495 — the shared duplicate-key classifier, pinned directly.

``agent/contracts/storage.py`` and ``storage/object_metadata.py`` each carried
this guess. It decides whether a caught exception means "already there" (retry
is idempotent) or "something else" (must be re-raised) — a wrong ``True`` hides
a real failure, so every branch gets a test.
"""
from __future__ import annotations

from storage.db_errors import is_duplicate_key


def test_mysql_dup_entry_code_is_a_duplicate() -> None:
    # PyMySQL puts ER_DUP_ENTRY (1062) in args[0] as an int.
    assert is_duplicate_key(Exception(1062, "Duplicate entry")) is True


def test_a_duplicate_entry_message_is_a_duplicate() -> None:
    assert is_duplicate_key(Exception("Duplicate entry 'x' for key 'PRIMARY'")) is True


def test_a_sqlite_unique_constraint_message_is_a_duplicate() -> None:
    assert is_duplicate_key(Exception("UNIQUE constraint failed: objects.id")) is True


def test_an_unrelated_error_is_not_a_duplicate() -> None:
    # Must be False, or the caller would swallow a real failure as "already there".
    assert is_duplicate_key(Exception("connection lost")) is False
    assert is_duplicate_key(Exception(2006, "server has gone away")) is False


def test_an_error_without_args_is_not_a_duplicate() -> None:
    assert is_duplicate_key(Exception()) is False


def test_the_code_must_be_the_integer_1062() -> None:
    # A *string* "1062" is not the driver's code; classifying it would be guessing.
    assert is_duplicate_key(Exception("1062")) is False
