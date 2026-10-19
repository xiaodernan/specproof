"""Fence: the optimization ledger must not gain NEW duplicate section numbers.

The ledger is an append-only record of what was true when each section was
written, so rewriting a historical header would violate its own contract. The
duplicates that already exist (``#144``/``#145`` are each a 「待办配方」+「落地」
pair, ``#246`` is a genuine reuse) are therefore kept as-is — but no NEW
duplicate may appear, and a known duplicate may not grow a third copy.

This is a one-way ratchet: fixing a historical duplicate is allowed (it just
shrinks the whitelist), adding one is not.

Sub-numbers (``#254b``, ``#173-1``, ``#173-2``) are distinct tokens and must not
be miscounted as duplicates of ``#254``/``#173``.
"""

import collections
import re
from pathlib import Path

_LEDGER = Path(__file__).resolve().parents[2] / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md"
_SECTION_RE = re.compile(r"^## #(\S+)", re.MULTILINE)

#: Historical duplicates, kept because the ledger is append-only.
#: ``144``/``145``: each is a 「待办配方」 + 「落地」 pair for one unit.
#: ``246``: two landed sections that reused the number.
_KNOWN_DUPLICATES = {"144", "145", "246"}

#: A ledger this small would make the duplicate check vacuous.
_MIN_SECTIONS = 100


def _tokens() -> list[str]:
    return _SECTION_RE.findall(_LEDGER.read_text(encoding="utf-8"))


def test_ledger_exists_and_has_sections():
    assert _LEDGER.is_file(), f"ledger missing: {_LEDGER}"
    tokens = _tokens()
    # non-empty denominator: an empty set must not read as "clean"
    assert len(tokens) >= _MIN_SECTIONS


def test_no_new_duplicate_section_numbers():
    counts = collections.Counter(_tokens())
    dups = {token: n for token, n in counts.items() if n > 1}
    new = set(dups) - _KNOWN_DUPLICATES
    assert not new, f"new duplicate section numbers: {sorted(new)}"


def test_known_duplicates_keep_their_count():
    counts = collections.Counter(_tokens())
    for token in _KNOWN_DUPLICATES:
        # a third copy of an already-known duplicate is still a new duplicate
        assert counts[token] == 2, f"#{token} appears {counts[token]} times, expected 2"


def test_sub_numbers_are_not_counted_as_duplicates():
    counts = collections.Counter(_tokens())
    dups = {token for token, n in counts.items() if n > 1}
    # #254b / #241b / #173-1 / #173-2 are distinct tokens, not duplicates.
    assert "254" not in dups
    assert "241" not in dups
    assert "173" not in dups


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
