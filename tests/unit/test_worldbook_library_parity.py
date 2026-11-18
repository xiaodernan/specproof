"""worldbook vs library — why the counts must differ by exactly one.

Measured 2026-11-19 (this tree, this commit):

  docs/world/SPECROOF_WORLD.md          → 203 `## ` sections (zh)
  docs/world/EN/SPECROOF_WORLD_EN.md    → 203 `## ` sections (en) — same order
  apps/web/src/pages/worldbook.json     → 204 volumes (zh: `front` + 203 chapters)
  apps/web/src/pages/worldbook.json     → 204 en volumes (mirror)
  apps/web/src/pages/library.json       → 203 zh ≡ 203 en (the 203 chapters,
                                         byte-compared, excluding the frontispiece)

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


def test_zh_and_en_bibles_carry_the_same_203_sections() -> None:
    zh = _bible_sections(ROOT / "docs" / "world" / "SPECROOF_WORLD.md")
    en = _bible_sections(ROOT / "docs" / "world" / "EN" / "SPECROOF_WORLD_EN.md")
    assert len(zh) == len(en)
    assert len(zh) == 203


def test_worldbook_volumes_is_frontispiece_plus_the_203_chapters() -> None:
    d = json.loads((ROOT / "apps" / "web" / "src" / "pages" / "worldbook.json").read_text(encoding="utf-8"))
    volumes = d["locales"]["zh"]["volumes"]
    assert len(volumes) == 204
    assert volumes[0]["id"] == "front"
    assert volumes[-1]["id"] == "vol-202"


def test_library_indexes_the_203_chapters_and_nothing_else() -> None:
    library = json.loads((ROOT / "apps" / "web" / "src" / "pages" / "library.json").read_text(encoding="utf-8"))
    assert library["count"] == 203
    assert len(library["zh"]) == 203
    assert len(library["en"]) == 203
    volumes = json.loads((ROOT / "apps" / "web" / "src" / "pages" / "worldbook.json").read_text(encoding="utf-8"))
    assert len(volumes["locales"]["zh"]["volumes"]) - library["count"] == 1
