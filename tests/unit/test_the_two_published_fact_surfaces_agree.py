"""The two published fact surfaces must not drift apart.

#2074 found them 35 entries apart after a ledger append: the browser's
``chronicle.json`` still held 1833 entries (last strike #2036) while
``docs/latest.json`` advertised 1868. ``test_next_step_advice.py`` did not
catch it because both its sides read the SAME ``chronicle.json`` — a leg whose
two operands share a source can never fail. This module reads the OTHER
surface (``latest.json``), which is built by a different script with a
different ruler, so a missed rebuild makes this gate go red honestly.

Regenerate both before claiming green:
    python scripts/build_chronicle.py
    python scripts/build_latest.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHRONICLE = REPO / "apps/web/src/pages/chronicle.json"
LATEST = REPO / "docs/latest.json"
LEDGER = REPO / "docs/operations/DEEP_OPTIMIZATION_PLAN.md"


def _load(path: Path):  # noqa: ANN202
    return json.loads(path.read_text(encoding="utf-8"))


def _ledger_numbers() -> set[int]:
    text = LEDGER.read_text(encoding="utf-8")
    return {int(m) for m in re.findall(r"(?m)^## #(\d+)\s", text)}


def test_the_two_published_entry_counts_are_equal() -> None:
    chronicle = _load(CHRONICLE)
    latest = _load(LATEST)
    assert isinstance(chronicle, list) and chronicle
    assert latest["chronicle_entries"] == len(chronicle), (
        "latest.json and chronicle.json were rebuilt at different times — "
        "run both build scripts; a published count must match the page it counts"
    )


def test_the_last_chronicle_strike_has_a_real_ledger_section() -> None:
    chronicle = _load(CHRONICLE)
    last = chronicle[-1]["n"]
    assert last in _ledger_numbers(), (
        f"chronicle ends at #{last} but the ledger has no ## #{last} section"
    )


def test_the_advertised_latest_strike_has_a_real_ledger_section() -> None:
    latest = _load(LATEST)
    strike = latest["latest_strike"]
    assert isinstance(strike, str) and strike.startswith("#")
    assert int(strike[1:]) in _ledger_numbers(), (
        f"latest.json advertises {strike} but the ledger has no such section"
    )


def test_the_two_published_surfaces_agree_on_the_newest_strike() -> None:
    # The page and the fact pack must point at the same newest strike, not
    # merely at a strike that exists somewhere in the ledger.
    chronicle = _load(CHRONICLE)
    latest = _load(LATEST)
    assert chronicle[-1]["n"] == int(latest["latest_strike"][1:])
