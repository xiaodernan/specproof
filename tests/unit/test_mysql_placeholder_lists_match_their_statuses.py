"""The SQL placeholder lists must have one hole per status.

The reaper's two queries interpolate a placeholder list into the SQL text
and pass the statuses themselves as bound parameters. The list is a
LITERAL, so the static prover can see that the SQL text is constant
(`tests/unit/test_sql_text_static.py`) — a computed list is one it
cannot follow.

A literal can drift away from the set it describes, and the drift is
silent: the query would fail on a parameter count, at 3 a.m., in the
reaper. These tests are that pin.
"""

from __future__ import annotations

from storage.mysql import (
    _EXPIRABLE_SQL_LIST,
    _EXPIRABLE_STATUS_ORDER,
    _IN_FLIGHT_SQL_LIST,
    _IN_FLIGHT_STATUS_ORDER,
    EXPIRABLE_STATUSES,
    IN_FLIGHT_STATUSES,
)


def test_the_in_flight_placeholder_list_has_one_hole_per_status() -> None:
    assert _IN_FLIGHT_SQL_LIST.count("%s") == len(_IN_FLIGHT_STATUS_ORDER)
    assert len(_IN_FLIGHT_STATUS_ORDER) == len(IN_FLIGHT_STATUSES)


def test_the_expirable_placeholder_list_has_one_hole_per_status() -> None:
    assert _EXPIRABLE_SQL_LIST.count("%s") == len(_EXPIRABLE_STATUS_ORDER)
    assert len(_EXPIRABLE_STATUS_ORDER) == len(EXPIRABLE_STATUSES)


def test_the_placeholder_lists_carry_no_status_text() -> None:
    """Only holes: a status name in the SQL text would be SQL built from
    data, which is the thing the placeholders exist to prevent."""
    for status in (*IN_FLIGHT_STATUSES, *EXPIRABLE_STATUSES):
        assert status not in _IN_FLIGHT_SQL_LIST
        assert status not in _EXPIRABLE_SQL_LIST
