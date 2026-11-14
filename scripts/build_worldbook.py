#!/usr/bin/env python
"""Build worldbook.json — the World Book (SPECROOF_WORLD) as a machine-readable payload for `#/worldbook`.

Reads both editions of the world bible and emits one JSON consumed by the
Reading Room page. Read-only with respect to the sources; if a source is
wrong, the page shows the wrong — it does not fix it.

Output:
    apps/web/src/pages/worldbook.json
    {
      "generated_by": "scripts/build_worldbook.py",
      "locales": {
        "zh": { "title": ..., "volumes": [ {"id", "num", "title", "markdown"} ] },
        "en": { ... }
      }
    }

Every volume is one `## ` section. Everything before the first `## ` heading
(book frontispiece / 序章) becomes volume id "front".
"""

import io
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "apps" / "web" / "src" / "pages" / "worldbook.json"

SOURCES = {
    "zh": REPO / "docs" / "world" / "SPECROOF_WORLD.md",
    "en": REPO / "docs" / "world" / "EN" / "SPECROOF_WORLD_EN.md",
}

_VOLUME_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


def parse_book(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # Book title = the first level-1 heading.
    title_match = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    title = title_match.group(1).strip() if title_match else path.name

    matches = list(_VOLUME_RE.finditer(text))
    volumes: list[dict] = []

    front_end = matches[0].start() if matches else len(text)
    front = text[:front_end].strip()
    # Drop the level-1 heading and the leading `---` rules from the frontispiece.
    front = re.sub(r"^#\s+.+?$", "", front, count=1, flags=re.M).strip().strip("-").strip()
    if front:
        volumes.append({"id": "front", "num": "", "title": "序章 · Frontispiece" if "SPECROOF" in title or "铁证" in title else "Frontispiece", "markdown": front})

    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip().strip("-").strip()
        head = m.group(1).strip()
        # Split "卷零 · 创世之炉" / "Volume XXI · The World ..." into num + title
        if "·" in head:
            num, title_part = head.split("·", 1)
            num, title_part = num.strip(), title_part.strip()
        else:
            num, title_part = "", head
        volumes.append({
            "id": f"vol-{idx:02d}",
            "num": num,
            "title": title_part,
            "markdown": body,
        })
    return {"title": title, "volumes": volumes}


def main() -> int:
    out: dict = {"generated_by": "scripts/build_worldbook.py", "locales": {}}
    for locale, path in SOURCES.items():
        if not path.is_file():
            print(f"missing source: {path}", file=sys.stderr)
            return 2
        book = parse_book(path)
        out["locales"][locale] = book
        total_chars = sum(len(v["markdown"]) for v in book["volumes"])
        print(f"{locale}: {len(book['volumes'])} volumes, {total_chars} chars of body")
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
