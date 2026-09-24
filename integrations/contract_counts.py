"""One rendering of the persisted contract counts, shared by every outward channel.

The GitHub Check Run summary and the notification templates both used to read
the same four counts with ``summary.get(key, 0)``. A summary that recorded no
counts therefore printed ``Contracts: 0 total — 0 passed, 0 failed,
0 unverified.`` — a confident claim that nothing was checked, which no reader
can tell apart from "this change touches no contract". The failure path made
that concrete by handing the renderer a dict with literal zeros in it.

Absence has exactly one rendering here: "not counted".
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

COUNT_KEYS: tuple[str, ...] = (
    "contracts_total",
    "matrix_passed",
    "matrix_failed",
    "matrix_unverified",
)

NOT_COUNTED = "not counted — this run recorded no contract statistics"


def _as_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def counted(summary: Mapping[str, Any]) -> dict[str, int] | None:
    """The four counts as ints, or None when any of them is not there.

    A partial record counts as "not counted" on purpose: a line that shows a
    total but no split would still be read as a complete tally.
    """
    stats: dict[str, int] = {}
    for key in COUNT_KEYS:
        value = _as_count(summary.get(key))
        if value is None:
            return None
        stats[key] = value
    return stats


def count_sentence(summary: Mapping[str, Any]) -> str:
    """"4 total — 3 passed, 1 failed, 0 unverified", or the absence note."""
    stats = counted(summary)
    if stats is None:
        return NOT_COUNTED
    return (
        f"{stats['contracts_total']} total — "
        f"{stats['matrix_passed']} passed, "
        f"{stats['matrix_failed']} failed, "
        f"{stats['matrix_unverified']} unverified"
    )
