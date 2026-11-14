#!/usr/bin/env python3
"""
sync_portfolio.py — 把 SpecProof master 的最新成果生成一份"落地书"（data-drop），供你
把 portfolio 页面定时 / 或在 master 大步向前时拉取或推送。

生成三份产物到 ./artifacts/portfolio-data/：

  1. .github-sync.json   —— portfolio 静态页面直接读；字段全是标量和 hash
  2. latest.md           —— markdown 格式的 "最近 ship" 一 liner（用于侧栏/列表）
  3. products.json       —— 在本地 pages 编译时可以直接展示的目录清单（routes、size、bills stats）

用法（每次 master 跑完大步 / 或 cron 拉取前）：
  python scripts/sync_portfolio.py

边界：
  - 不写 portfolio repo、不调用网络、不碰任何密钥；
  - 输出的三份文件里没有任何敏感信息（无 .env、无 token、无私有 prompt）；
  - 不可见的分支也不会出现在产物里——读的是 .git。
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "portfolio-data"


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _ledger_first_heading() -> str:
    text = (ROOT / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md").read_text(encoding="utf-8")
    # Latest entry is appended at EOF — take the tail and scan for the last ## number heading.
    tail = text[-6000:]
    m = re.search(r"\n## (#\d+[^\n]+)", tail)
    return m.group(1) if m else "(none)"


def _pages() -> list[str]:
    pdir = ROOT / "apps" / "web" / "src" / "pages"
    return sorted(
        f.stem for f in pdir.glob("*.tsx")
        if f.stem != "__tests__" and not f.stem.startswith("_") and not f.stem.endswith(".test")
    )


def _world_bytes() -> int:
    w = ROOT / "docs" / "world" / "SPECROOF_WORLD.md"
    return w.stat().st_size if w.exists() else 0


def _latest_changelog() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # Match the last "## ..." block — just its first 2-3 lines
    m = re.search(r"\n## ([^\n]+)\n", text)
    return m.group(1) if m else "(no changelog entry parsed)"


def _e2e_passed_at() -> str:
    # cheap: find the latest modified e2e spec under tests/e2e whose body references a green date
    p = ROOT / "tests" / "e2e"
    try:
        out = subprocess.run(
            ["git", "-C", str(p), "log", "-n", "1", "--format=%ad", "--date=short", "--", str(p)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return out.stdout.strip() or "(undetermined)"
    except Exception:
        return "(undetermined)"


def main() -> None:
    latest_tag = _git("describe", "--tags", "--abbrev=7", "--always", "HEAD") or _git("describe", "--al ---abbrev=7", "--always", "HEAD")
    latest_branch = _git("branch", "--show-current")
    latest_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "schema": 1,
        "last_synced": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": latest_branch,
        "head": _git("rev-parse", "--short", "HEAD"),
        "latest_day": latest_day,
        "latest_tag": latest_tag,
        "latest_ledger_entry": _ledger_first_heading(),
        "latest_changelog": _latest_changelog(),
        "world_size_bytes": _world_bytes(),
        "page_count": len(_pages()),
        "pages": _pages(),
        "e2e_last_touch": _e2e_passed_at(),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    OUT / ".github-sync.json", OUT / "latest.md", OUT / "products.json"

    (OUT / ".github-sync.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    ledger_title = payload["latest_ledger_entry"]
    latest_md = f"""## SpecProof · 最新一次 ship

**{payload['latest_day']} · {payload['head']}**
- 分支: `{payload['branch']}`
- ledger: `{ledger_title}`
- 世界书: `docs/world/SPECROOF_WORLD.md`（{payload['world_size_bytes']/1024:.1f} KB）
- 页面: {payload['page_count']} 个模块
- changelog: {payload['latest_changelog']}

[→ 世界观目录 (EN & 中)](./docs/world/README.md)
[→ SPECROOF 完整手册](./docs/operations/USER_GUIDE.md)
"""
    (OUT / "latest.md").write_text(latest_md, encoding="utf-8")

    products = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pages": [
            {"path": f"/#/{name}", "component": name} for name in payload["pages"]
        ],
    }
    (OUT / "products.json").write_text(
        json.dumps(products, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("wrote:", OUT / ".github-sync.json")
    print("wrote:", OUT / "latest.md")
    print("wrote:", OUT / "products.json")
    print(f"world_size: {payload['world_size_bytes']/1024:.1f} KB; page_count: {payload['page_count']}")


if __name__ == "__main__":
    main()
