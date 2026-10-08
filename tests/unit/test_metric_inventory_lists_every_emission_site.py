"""Gate: OBSERVABILITY.md 8.10's inventory must BE the emission census (#217).

Section 8.10 ("已接线指标名") declares its own provenance rule: this project
has no static metric registry, a name appears on /metrics only after its
first emission, so "这份清单的唯一合法来源是上报点，不是本文件". The list is
therefore supposed to be a faithful per-file inventory of the modules that
own an emission site — and the section also states a hand-typed module count
("生产侧上报模块有三十三个") that has been re-corrected fourteen times as
each arc wired a new tree, always by hand.

That is the same drift class #216 found in section 5's alert table: two
hand-maintained copies of one fact, with no gate between them. Measured
before this test existed (#217): the census held 34 files while the list
named 33 — ``storage/mysql.py`` emits two meters
(``notify_outbox_enqueued_total`` / ``notify_outbox_intent_lost_total`` in
``transition_job_status_with_notify``) but had no bullet at all; it survived
only as a parenthetical inside the ``notify_relay`` bullet, so a reader using
the list as the inventory could not see that mysql.py reports.

The census itself is not re-derived here: ``emission_files`` is imported from
the parity gate, which owns EMIT_DIRS and the call-shape scan. Growing that
inventory moves both gates together.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.unit.test_observability_metric_parity import emission_files

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "operations" / "OBSERVABILITY.md"

#: The heading that opens the inventory; the list runs to the next `## `.
_HEADING = "已接线指标名"

#: The hand-typed count sentence. Chinese numerals only reach the tens here.
_COUNT = re.compile(r"生产侧上报模块有([一二三四五六七八九十]+)个")

_CN_DIGITS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}


def _cn_number(word: str) -> int:
    """``三十四`` -> 34, ``三十`` -> 30, ``十七`` -> 17."""
    if "十" not in word:
        return _CN_DIGITS[word]
    tens, _, ones = word.partition("十")
    return (_CN_DIGITS.get(tens, 1) * 10) + (_CN_DIGITS.get(ones, 0) if ones else 0)


def _inventory_bullets() -> list[str]:
    """The file paths named by the 8.10 bullet list, duplicates kept."""
    doc = DOC.read_text(encoding="utf-8")
    assert _HEADING in doc, f"inventory heading {_HEADING!r} moved — probe broken"
    section = doc.split(_HEADING, 1)[1].split("\n## ", 1)[0]
    bullets = re.findall(r"^- `([^`]+)`", section, re.M)
    # A collapsed parse (regex stops matching) must not read as "no problem".
    assert len(bullets) >= 20, (
        f"inventory parse collapsed: {len(bullets)} bullets found in section "
        f"{_HEADING!r} — the bullet shape moved"
    )
    return [b.split("::", 1)[0].strip() for b in bullets]


def test_the_inventory_names_every_emission_site() -> None:
    """Both directions: nothing emitted is missing, nothing named is dead."""
    listed = set(_inventory_bullets())
    census = emission_files()

    missing = sorted(census - listed)
    dead = sorted(listed - census)

    assert not missing, (
        "8.10's inventory omits modules that own an emission site — the "
        "section calls the emission sites its only legal source, so a "
        f"missing entry makes the meter invisible to the list: {missing}"
    )
    assert not dead, (
        "8.10's inventory names files with no emission site — either the "
        "meter moved (fix the entry) or the bullet is stale: "
        f"{dead}"
    )


def test_the_stated_count_matches_the_inventory() -> None:
    """The hand-typed count must equal the list's unique file count.

    The count is about files ("每个列出文件计一次、重复条目不计"), so a
    second bullet for one file (review_court.py has two, #180 and #184) must
    not inflate it.
    """
    doc = DOC.read_text(encoding="utf-8")
    match = _COUNT.search(doc)
    assert match is not None, "the module-count sentence moved — probe broken"

    stated = _cn_number(match.group(1))
    listed = set(_inventory_bullets())

    assert stated == len(listed), (
        f"the stated module count ({match.group(1)} = {stated}) disagrees with "
        f"the inventory's {len(listed)} unique files — one of the two copies "
        "drifted; fix both together"
    )
