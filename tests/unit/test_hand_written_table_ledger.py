"""A register of modules that still hand-roll a <table>, and a refusal to let it grow.

ui/Table.tsx is the design-system table. Every other module that writes its own <table>
inherits none of its overflow/scroll behaviour, which is how a long-reason cell breaks a
page. Rather than claim the debt is paid, this gate keeps the exact list of debtors red:
a new hand-rolled table is refused, and a listed file that stopped hand-rolling one is
refused too, so the register cannot silently rot into a description of a codebase that no
longer exists.

Population measured at commit 84e02e8: 5 sites across 4 files
(agent/pages/AgentEventLog.tsx:43, agent/pages/AgentPlanReview.tsx:48,
pages/Dashboard.tsx:65, pages/FindingDetail.tsx:212 and :318).

Paid off since, one site per commit, each with the file leaving the register:
  * pages/FindingDetail.tsx — the reviewer ledger moved to ui/Table (14335d3),
    then the evidence panel moved to kv() rows, so the file is out. What is left:
    3 sites across 3 files (AgentEventLog.tsx:43, AgentPlanReview.tsx:48,
    Dashboard.tsx:65).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WEB_SRC = REPO / "apps/web/src"
SHARED_TABLE = WEB_SRC / "ui/Table.tsx"

# The files that still hand-roll a table, measured at the commit this test landed on.
HAND_WRITTEN_TABLE_DEBT = {
    "agent/pages/AgentEventLog.tsx",
    "agent/pages/AgentPlanReview.tsx",
    "pages/Dashboard.tsx",
}


def hand_rolled_table_sites() -> dict[str, int]:
    sites: dict[str, int] = {}
    for path in sorted(WEB_SRC.rglob("*.tsx")):
        if ".test." in path.name:
            continue
        if path == SHARED_TABLE:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        count = text.count("<table")
        if count:
            sites[path.relative_to(WEB_SRC).as_posix()] = count
    return sites


def test_the_shared_table_component_still_renders_the_shared_markup() -> None:
    # The exemption below only means something if this file really is the component
    # everyone is supposed to reuse, so the exemption is checked, not assumed.
    text = SHARED_TABLE.read_text(encoding="utf-8")
    assert "<table" in text and "tableCls" in text, (
        "ui/Table.tsx no longer renders the shared table markup, so exempting it by "
        "path hides a different component"
    )


def test_no_new_module_hand_rolls_a_table() -> None:
    found = set(hand_rolled_table_sites())
    extra = sorted(found - HAND_WRITTEN_TABLE_DEBT)
    assert not extra, (
        f"hand-rolled <table> appeared in {extra}; render through ui/Table so cell "
        "overflow and scroll behaviour is inherited instead of re-invented"
    )


def test_the_debt_register_is_not_lying() -> None:
    found = set(hand_rolled_table_sites())
    stale = sorted(HAND_WRITTEN_TABLE_DEBT - found)
    assert not stale, (
        f"{stale} no longer hand-roll a table; drop them from the register so it keeps "
        "describing real debt (paying one off is a win -- record it and shrink the list)"
    )


def test_the_scan_actually_read_something() -> None:
    sites = hand_rolled_table_sites()
    assert sites, "no hand-rolled table found at all -- the scan read nothing, or moved"
    assert sum(sites.values()) >= len(HAND_WRITTEN_TABLE_DEBT), (
        f"only {sum(sites.values())} hand-rolled table sites counted across "
        f"{len(sites)} files, below the {len(HAND_WRITTEN_TABLE_DEBT)} registered files; "
        "the population shrank without the register being updated"
    )


@pytest.mark.parametrize("path", sorted(HAND_WRITTEN_TABLE_DEBT))
def test_each_debtor_is_named_by_its_real_path(path: str) -> None:
    assert (WEB_SRC / path).is_file(), f"{path} is in the register but does not exist"
