"""Honesty gate for the offline ask-the-book snapshot.

The AskTheBook page falls back to `askthebook_snapshot.json` when the live
model lane is unavailable. If a snapshot entry carried text that never
appears in the world book, a user asking offline would be reading invented
prose labelled “书里原文 · verbatim from the World Book”. This gate forbids
exactly that:
  * schema completeness across the eight canned answers (no silent stubs),
  * every entry's excerpt must be a verbatim slice of the committed world
    book (docs/world/**/*.md) — modulo only whitespace normalization,

runs offline, and is byte-identical between CI and this host.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "apps" / "web" / "src" / "pages" / "askthebook_snapshot.json"
WORLD_FILES = sorted((ROOT / "docs" / "world").rglob("*.md"))
EXPECTED_KEYS = {"id", "excerpt", "keywords_zh", "keywords_en", "volume"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.fixture(scope="module")
def books() -> list[str]:
    return [_norm(path.read_text(encoding="utf-8", errors="replace")) for path in WORLD_FILES]


@pytest.fixture(scope="module")
def snap() -> list[dict]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_schema_is_complete(snap: list[dict]) -> None:
    assert snap, "snapshot is empty"
    seen: set[str] = set()
    for item in snap:
        assert set(item) >= EXPECTED_KEYS, f"{item.get('id')} missing keys"
        for key in EXPECTED_KEYS:
            assert item[key], f"{item.get('id')} — empty field {key}"
        assert len(item["excerpt"]) >= 80, f"{item.get('id')} excerpt below floor"
        assert all(kw.strip() for kw in item["keywords_zh"] + item["keywords_en"]), \
            f"{item.get('id')} — blank keyword"
        seen.add(item["id"])
    assert len(seen) == len(snap), "duplicate ids in snapshot"


def test_every_entry_is_a_verbatim_slice(snap: list[dict], books: list[str]) -> None:
    """Every answer the offline fallback can show is a literal slice of the book."""
    misses: list[str] = []
    for item in snap:
        needle = _norm(item["excerpt"])
        if not any(needle in book for book in books):
            misses.append(item["id"])
    assert not misses, (
        "these snapshot entries quote text that does NOT appear in the \
committed world book — the offline fallback would be fabricating prose: "
        + ", ".join(misses)
    )


def test_snapshot_language_pairs_exist(snap: list[dict]) -> None:
    for item in snap:
        zh = item.get("keywords_zh") or []
        en = item.get("keywords_en") or []
        assert zh and en, f"{item.get('id')} must carry both zh and en keyword sets"
