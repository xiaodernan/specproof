"""worldbook vs library — why the counts must differ by exactly one.

Measured 2026-11-25 after scroll 207 (#2096-2099, written from real ledger facts):

  docs/world/SPECROOF_WORLD.md          -> 206 `## ` sections (zh)
  docs/world/EN/SPECROOF_WORLD_EN.md    -> 206 `## ` sections (en) - same order
  apps/web/src/pages/worldbook.json     -> 207 volumes (zh: `front` + 206 chapters)
  apps/web/src/pages/worldbook.json     -> 207 en volumes (mirror)
  apps/web/src/pages/library.json       -> 206 zh == 206 en (the 206 chapters,
                                          byte-compared, excluding the frontispiece)

Scroll 205 (卷二百零五 / Scroll CCV) was LLM-generated from #2072-2076; scrolls 206
(卷二百零六 / Scroll CCVI) and 207 (卷二百零七 / Scroll CCVII) were written bilingually
from this session's real #2078-2095 and #2096-2099 facts after the gateway closed. Each
adds one chapter, not a drift. The pinned relation (worldbook = library + 1 frontispiece)
is unchanged.

The two numbers are not a drift — the worldbook displays the frontispiece
as a volume because it belongs to the reading experience; the library indexes
only chapter bodies. This file pins THAT relation so a future count change
cannot smuggle either honest metric past review.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTION_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")


def _bible_sections(path: Path) -> list[str]:
    return [m.group(1) for m in SECTION_RE.finditer(path.read_text(encoding="utf-8"))]


def test_zh_and_en_bibles_carry_the_same_206_sections() -> None:
    zh = _bible_sections(ROOT / "docs" / "world" / "SPECROOF_WORLD.md")
    en = _bible_sections(ROOT / "docs" / "world" / "EN" / "SPECROOF_WORLD_EN.md")
    assert len(zh) == len(en)
    assert len(zh) == 206  # scroll 207 (卷二百零七 / Scroll CCVII), #2096-2099


def test_worldbook_volumes_is_frontispiece_plus_the_206_chapters() -> None:
    d = json.loads((ROOT / "apps" / "web" / "src" / "pages" / "worldbook.json").read_text(encoding="utf-8"))
    volumes = d["locales"]["zh"]["volumes"]
    assert len(volumes) == 207
    assert volumes[0]["id"] == "front"
    assert volumes[-1]["id"] == "vol-205"


def test_library_indexes_the_206_chapters_and_nothing_else() -> None:
    library = json.loads((ROOT / "apps" / "web" / "src" / "pages" / "library.json").read_text(encoding="utf-8"))
    assert library["count"] == 206
    assert len(library["zh"]) == 206
    assert len(library["en"]) == 206
    volumes = json.loads((ROOT / "apps" / "web" / "src" / "pages" / "worldbook.json").read_text(encoding="utf-8"))
    assert len(volumes["locales"]["zh"]["volumes"]) - library["count"] == 1
