"""The one producer of the canonical UTC timestamp string this product writes.

#516 measured five copies of this exact shape across three packages — three in
`evidence/`, one in `contracts/events.py`, one in `experiments/collectors.py` —
and the clone ratchet never compared four of them: its package census omitted
`contracts/` altogether, and the `experiments/` copy hides behind a lazy
`from datetime import ...` that makes its AST different while its output is
identical.

The format is a wire contract, not a local convenience: it is what
`occurred_at`, `collected_at`, `started_at`, `finished_at` and `verified_at`
carry, so a drifted copy does not fail a check — it writes a payload whose
timestamps two producers disagree about, and the disagreement only surfaces
when a consumer sorts or compares them.

Contracts is the lowest package that can own this (it imports stdlib only, and
`experiments/` already reaches `evidence/`, which already reaches `contracts/`
through `storage/`). Two other timestamp vocabularies live in the product and are
deliberately NOT folded in here, because folding them would change what clients
read: 30 no-argument `datetime.now(UTC).isoformat()` call sites across 22 modules
(microseconds + `+00:00`), and 7 identical
`datetime.now(UTC).isoformat(timespec="seconds")` sites across 6 `craft/` modules.
"""
from __future__ import annotations

from datetime import UTC, datetime


def utc_now_iso() -> str:
    """UTC, millisecond precision, `Z` suffix — the guide's timestamp format."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = ["utc_now_iso"]
