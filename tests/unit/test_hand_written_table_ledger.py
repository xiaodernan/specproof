"""A register of modules that still hand-roll a <table>, and a demand that each be accounted for.

ui/Table.tsx is the design-system table. Every other module that writes its own <table>
inherits none of its overflow/scroll behaviour, which is how a long-reason cell breaks a
page. #122 asks one of two things of every hand-rolled table: migrate it to ui/Table, or
show that the failure mode cannot happen there. This gate refuses a new unaccounted table
and refuses a listed file that stopped hand-rolling one, so the register cannot rot into a
description of a codebase that no longer exists.

Population measured at commit 84e02e8: 5 sites across 4 files
(agent/pages/AgentEventLog.tsx:43, agent/pages/AgentPlanReview.tsx:48,
pages/Dashboard.tsx:65, pages/FindingDetail.tsx:212 and :318).

Paid off one site per commit, the file leaving HAND_WRITTEN_TABLE_DEBT each time:
  * pages/FindingDetail.tsx -- reviewer ledger to ui/Table (14335d3), then the evidence
    panel to kv() rows (55b37d3);
  * agent/pages/AgentEventLog.tsx -- event log to ui/Table (0d4c0af);
  * agent/pages/AgentPlanReview.tsx -- step table to ui/Table (70f9b5c).

HAND_WRITTEN_TABLE_DEBT is empty on purpose: an empty debt list is this thread's goal, not
a failure of the scan. The one hand-rolled table left, pages/Dashboard.tsx:65, is in
CONTAINED_HAND_ROLLED_TABLES instead -- #122's complaint is an unbreakable value with no
scroll container, and the measurements re-checked below say it has one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WEB_SRC = REPO / "apps/web/src"
SHARED_TABLE = WEB_SRC / "ui/Table.tsx"

# How many .tsx files the scan reads, measured at 70f9b5c. A floor, not an equality: it
# exists to catch the scan itself breaking (wrong root, moved package, a glob that stops
# matching), because an empty site list from a broken scan is not the same thing as no
# hand-rolled tables left.
SCANNED_TSX_MEASURED_AT_70f9b5c = 75
SCANNED_TSX_FLOOR = 40

# Files that hand-roll a <table> and must be migrated to ui/Table. Empty on purpose; a
# name reappearing here is new debt.
HAND_WRITTEN_TABLE_DEBT: set[str] = set()

# Hand-rolled tables accounted for by a proof instead of a migration: the markup is
# wrapped in a scroll container, that container's class really does carry `overflow`, and
# the layout track holding it may shrink below its min-content width. Drop any of the
# three and a long unbroken cell widens the page again, so all three are re-measured
# below rather than trusted to a note someone wrote once.
CONTAINED_HAND_ROLLED_TABLES = {
    "pages/Dashboard.tsx": {
        # <div className="table-scroll"><table className="data"> ...
        "wrapper_class": "table-scroll",
        "css": "styles/product.css",
        "overflow_rule": ".table-scroll { overflow-x: auto; }",
        # `2.1fr` alone would make this track's min-content width come from its widest
        # cell, i.e. the page widens anyway, overflow or not. `minmax(0, ...)` is the half
        # that actually buys the scrolling.
        "shrinking_track_rule": (
            ".dashboard-bottom { display: grid; "
            "grid-template-columns: minmax(0, 2.1fr) minmax(250px, 1fr);"
        ),
    },
}


def scanned_tsx_files() -> list[Path]:
    return [
        path
        for path in sorted(WEB_SRC.rglob("*.tsx"))
        if ".test." not in path.name and path != SHARED_TABLE
    ]


def hand_rolled_table_sites() -> dict[str, int]:
    sites: dict[str, int] = {}
    for path in scanned_tsx_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        count = text.count("<table")
        if count:
            sites[path.relative_to(WEB_SRC).as_posix()] = count
    return sites


def accounted_files() -> set[str]:
    return set(HAND_WRITTEN_TABLE_DEBT) | set(CONTAINED_HAND_ROLLED_TABLES)


def test_the_shared_table_component_still_renders_the_shared_markup() -> None:
    # The exemption below only means something if this file really is the component
    # everyone is supposed to reuse, so the exemption is checked, not assumed.
    text = SHARED_TABLE.read_text(encoding="utf-8")
    assert "<table" in text and "tableCls" in text, (
        "ui/Table.tsx no longer renders the shared table markup, so exempting it by "
        "path hides a different component"
    )


def test_every_hand_rolled_table_is_accounted_for() -> None:
    found = set(hand_rolled_table_sites())
    unaccounted = sorted(found - accounted_files())
    assert not unaccounted, (
        f"hand-rolled <table> appeared in {unaccounted} without being accounted for; "
        "render through ui/Table, or add the file to CONTAINED_HAND_ROLLED_TABLES with "
        "the wrapper class and the CSS rules that keep its longest cell from widening "
        "the page"
    )
    stale = sorted(accounted_files() - found)
    assert not stale, (
        f"{stale} are listed but no longer hand-roll a table; drop them so this register "
        "keeps describing real debt (paying one off is a win -- record it and shrink the "
        "list)"
    )


def test_contained_hand_rolled_tables_are_still_contained() -> None:
    for rel, spec in sorted(CONTAINED_HAND_ROLLED_TABLES.items()):
        source = (WEB_SRC / rel).read_text(encoding="utf-8", errors="replace")
        wrapper = 'className="' + spec["wrapper_class"] + '"'
        assert wrapper in source, (
            f"{rel} no longer wraps its table in {wrapper}, so the containment credited "
            "to this file is about markup that is not there any more"
        )
        opened = source.index(wrapper)
        assert "<table" in source[opened : opened + 200], (
            f"{rel}: {wrapper} is not the element wrapping the <table>, so the container "
            "this register credits is not the one holding the table"
        )
        css = (WEB_SRC / spec["css"]).read_text(encoding="utf-8", errors="replace")
        assert spec["overflow_rule"] in css, (
            f"{spec['overflow_rule']} is gone from {spec['css']}, so "
            f".{spec['wrapper_class']} no longer scrolls and a long unbroken cell in "
            f"{rel} widens the page again"
        )
        assert spec["shrinking_track_rule"] in css, (
            f"{spec['shrinking_track_rule']} is gone from {spec['css']}; without a grid "
            "track that may shrink to 0, an overflowing cell still sets the track's "
            f"min-content width and {rel} widens the page"
        )


def test_the_scan_actually_read_something() -> None:
    scanned = scanned_tsx_files()
    assert len(scanned) >= SCANNED_TSX_FLOOR, (
        f"the scan read only {len(scanned)} .tsx files (measured "
        f"{SCANNED_TSX_MEASURED_AT_70f9b5c} at 70f9b5c, floor {SCANNED_TSX_FLOOR}); the "
        "scan itself moved or broke. This asserts what the scan did, not what it found "
        "-- reading an empty register as a failure would block the outcome this thread "
        "is trying to reach"
    )


@pytest.mark.parametrize("path", sorted(accounted_files()))
def test_each_accounted_file_is_named_by_its_real_path(path: str) -> None:
    assert (WEB_SRC / path).is_file(), f"{path} is in the register but does not exist"
