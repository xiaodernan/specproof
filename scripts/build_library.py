#!/usr/bin/env python3
"""Build library.json — every volume in the world bible, machine-readable.

Lands an in-app reading guide: every `## 卷 / Scroll` chapter of the bilingual
SPECROOF_WORLD bible, with its heading and its first paragraph. No number is
invented, no volume is dropped, no chapter text is edited — the library shows
what the bible actually says, byte for byte, once enrolled.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
ZH = ROOT / "docs" / "world" / "SPECROOF_WORLD.md"
EN = ROOT / "docs" / "world" / "EN" / "SPECROOF_WORLD_EN.md"
OUT = ROOT / "apps" / "web" / "src" / "pages" / "library.json"

SECTION_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")


def _chapter_excerpt(body: str, limit: int = 240) -> str:
    for ln in body.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and not ln.startswith(">") and not ln.startswith("|"):
            return (ln[:limit] + ("…" if len(ln) > limit else "")).strip()
    return ""


def _parse(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    matches = list(SECTION_RE.finditer(text))
    volumes: list[dict] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip().strip("-").strip()
        volumes.append({
            "num": match.group(1).split(" · ", 1)[0],
            "title": match.group(1).split(" · ", 1)[1] if " · " in match.group(1) else match.group(1),
            "excerpt": _chapter_excerpt(body),
        })
    return volumes


def main() -> int:
    zh_volumes = _parse(ZH)
    en_volumes = _parse(EN)
    if len(zh_volumes) != len(en_volumes):
        print(
            f"worldbook drift: zh has {len(zh_volumes)} scrolls, en has {len(en_volumes)} — refusing to ship a lie",
            file=sys.stderr,
        )
        return 1
    if any(not v["title"] for v in zh_volumes) or any(not v["title"] for v in en_volumes):
        print("a volume had no title after the separator — check the volume headers", file=sys.stderr)
        return 1
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "count": len(zh_volumes),
        "zh": zh_volumes,
        "en": en_volumes,
        "note": "machine-struck from the two bibles; parity asserted at build time; never an editorial statement",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(zh_volumes)} scrolls zh≡en)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
