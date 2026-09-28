"""The feedback verdict vocabulary has three owners; this gate keeps them one word-list.

Side A reads the stored ENUM from the migrations through the reader the severity gate
already uses (imported, never re-typed). Side B reads the unions the API client declares.
Side C reads the label map the UI renders from. Any divergence is a red, and so is a
silently empty read.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.unit.test_severity_vocabulary_parity import enum_columns

REPO = Path(__file__).resolve().parents[2]
API_CLIENT = REPO / "apps/web/src/api.ts"
UTIL = REPO / "apps/web/src/ui/util.tsx"
PAGES = REPO / "apps/web/src/pages"

_INTERFACE_RE = re.compile(r"^export interface (\w+) \{(.*?)\n\}", re.S | re.M)
_VERDICT_RE = re.compile(r"^\s*verdict:\s*(.+);\s*$", re.M)
_QUOTED_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"')
_LABEL_MAP_RE = re.compile(
    r"const FEEDBACK_VERDICT_LABELS: Record<string, string> = \{(.*?)\n\}", re.S
)
_ENTRY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\"", re.M)
_KEY_LINE_RE = re.compile(r'^\s{2}[A-Za-z_][A-Za-z0-9_]*\s*:\s*"', re.M)
_TERNARY_RE = re.compile(r'===\s*"accept"\s*\?')


def stored_verdicts() -> set[str]:
    columns = enum_columns()
    stored = columns.get("finding_feedback.verdict")
    assert stored, "finding_feedback.verdict ENUM not parsed -- the probe is broken"
    return stored


def client_verdicts() -> set[str]:
    text = API_CLIENT.read_text(encoding="utf-8")
    # Scoped by DECLARING TYPE, not by field name: api.ts:695 declares a wide
    # `verdict: string` on a different interface (a run's own conclusion, whose words are
    # VERIFIED/BLOCKED/FAILED). Reading every `verdict:` field would compare two
    # vocabularies that were never the same question -- that is what refused this landing.
    blocks = [
        (m.group(1), m.group(2))
        for m in _INTERFACE_RE.finditer(text)
        if m.group(1).startswith("Feedback")
    ]
    assert blocks, "no Feedback* interface found in api.ts -- probe broken"
    groups: list[set[str]] = []
    for name, body in blocks:
        for m in _VERDICT_RE.finditer(body):
            tokens = set(_QUOTED_RE.findall(m.group(1)))
            assert tokens, f"{name}.verdict has no quoted words: {m.group(1)!r}"
            groups.append(tokens)
    assert len(groups) >= 3, (
        f"only {len(groups)} feedback verdict declarations read -- the reader went blind"
    )
    assert all(g == groups[0] for g in groups), (
        "api.ts declares more than one feedback verdict union, so one consumer could "
        f"accept a word another rejects: {sorted({frozenset(g) for g in groups})}"
    )
    return groups[0]


def label_verdicts() -> set[str]:
    text = UTIL.read_text(encoding="utf-8")
    block = _LABEL_MAP_RE.search(text)
    assert block, "FEEDBACK_VERDICT_LABELS not found in ui/util.tsx -- probe broken"
    keys = [m.group(1) for m in _ENTRY_RE.finditer(block.group(1))]
    # Two independent readers: one parser silently finding nothing must not read as
    # "the map is empty".
    counted = len(_KEY_LINE_RE.findall(block.group(1)))
    assert counted == len(keys), (
        f"label map readers disagree ({len(keys)} via _ENTRY_RE, {counted} via _KEY_LINE_RE)"
    )
    assert keys, "FEEDBACK_VERDICT_LABELS parsed as empty -- the probe is broken"
    return set(keys)


def test_client_union_matches_the_stored_enum() -> None:
    assert client_verdicts() == stored_verdicts(), (
        "the API client and the MySQL ENUM disagree about which verdicts exist, so a "
        "vote could be rejected by the database or silently truncated"
    )


def test_every_stored_verdict_has_a_label() -> None:
    missing = stored_verdicts() - label_verdicts()
    assert not missing, (
        f"stored verdict(s) {sorted(missing)} would render as a raw English token"
    )


def test_no_label_for_an_unstored_verdict() -> None:
    dead = label_verdicts() - stored_verdicts()
    assert not dead, (
        f"label(s) {sorted(dead)} name a verdict the column cannot hold -- a dead word "
        "the UI would never reach"
    )


def test_no_binary_ternary_invents_a_verdict() -> None:
    sites = [
        p.relative_to(REPO).as_posix()
        for p in PAGES.rglob("*.tsx")
        if _TERNARY_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert not sites, (
        "a binary `verdict === \"accept\" ? ... : ...` renders every unknown value "
        f"(empty, typo, future word) as 打回; use feedbackVerdictLabel instead: {sites}"
    )


def test_the_replacement_is_actually_used() -> None:
    used = sorted(
        p.relative_to(REPO).as_posix()
        for p in PAGES.rglob("*.tsx")
        if "feedbackVerdictLabel(" in p.read_text(encoding="utf-8")
    )
    assert used, (
        "no page calls feedbackVerdictLabel -- the honest renderer is dead code and the "
        "ternary ban above would be guarding nothing"
    )
