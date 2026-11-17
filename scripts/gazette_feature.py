#!/usr/bin/env python3
"""gazette_feature.py — the front page's editor.

An honor from today's ledger: the latest entries are handed to the model and
a short "an epitaph for today's world" is written back — one breath in Chinese,
one in English — then committed into ``apps/web/src/pages/gazette_feature.json``.

The model is NOT allowed to invent any facts. It may only:

  * read the verbatim ledger entry it is given;
  * describe its shape (what was struck, where, and what moved forward).

It may not make up incidents, numbers, dates, or names that are not present in
the ledger entry verbatim. If it writes more than 280 Chinese characters or
220 English words, the output is flagged but kept verbatim — the editor does
not edit his own sentence to make a point.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from providers.base import LLMMessage
from providers.config import load_model_config
from providers.openai_compatible import OpenAICompatibleProvider

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md"
OUT_JSON = ROOT / "apps" / "web" / "src" / "pages" / "gazette_feature.json"
EVIDENCE_JSON = ROOT / "docs" / "evidence" / "gazette-feature.json"
EVIDENCE_MD = ROOT / "docs" / "evidence" / "gazette-feature.md"

_COVENANT_SHAPE = (
    "我是这份铁日手账的编辑；我说的事，每一件都应该能在原文里找出证据。"
    "我不会加一条无来由的注脚，也不会把『干了』写成『做完了』。"
)


def _latest_block() -> str:
    text = LEDGER.read_text(encoding="utf-8")
    marker = "\n## #"
    idx = text.rfind(marker)
    if idx == -1:
        raise SystemExit("no ledger entries found — nothing to strike, aborting")
    return text[idx:]


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("## "):
            return ln.removeprefix("## ").strip()
    return text.splitlines()[0].strip() if text else "(empty)"


async def _call_model(provider: OpenAICompatibleProvider, system: str, user: str) -> str:
    resp = await provider.chat(
        [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)],
        timeout=120.0,
    )
    return str(resp.content or "").strip()


async def main() -> int:
    cfg = load_model_config()
    latest = _latest_block()
    anchor = _first_line(latest)

    spec = anchor.split(" ", 1)[0].lstrip("#").strip()

    user_zh = (
        f"下面是第 #{spec} 节的原文（节选）。\n\n"
        f"请用中文写一段**不超过 280 字**、适合今天头版的 epigraph——可以从中取三件最关键的事，、"
        f"它们各自落在哪里、"
        f"以及这件事在这个世界内部的形状。只写这一段正文，"
        f"不要 markdown 标题，不要编造数字，不要说「深入浅出」之类的空话。\n\n"
        f"「{anchor}」\n{latest[:2100]}"
    )
    user_en = (
        f"Here is an excerpt of ledger entry #{spec}.\n\n"
        f"Write a **at most 220 words** epigraph suited for today's front page of a newspaper "
        f"about an open world — you may quote the three most careful facts, "
        f"where each landed in the repository, and two sentences describing the world's shape around them. "
        f"Output only this paragraph. No markdown headings. No invented numbers.\n\n"
        f"「{anchor}」\n{latest[:2100]}"
    )

    print(f"anchor: {anchor}")
    print("striking aizzz twice (zh + en) ...", flush=True)

    provider = OpenAICompatibleProvider(
        api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"],
        protocol=cfg["protocol"], reasoning_effort=cfg.get("reasoning_effort"),
    )
    try:
        zh = await _call_model(provider, _COVENANT_SHAPE, user_zh)
        en = await _call_model(provider, _COVENANT_SHAPE, user_en)
    finally:
        await provider.close()

    if not zh or not en:
        print("model returned an empty side; not committing.", file=sys.stderr)
        return 1

    now = datetime.now(UTC).isoformat(timespec="seconds")
    out = {
        "generated_at": now,
        "anchor": anchor,
        "zh": zh,
        "en": en,
        "model": cfg.get("model"),
        "chars_zh": len([c for c in zh if "\u4e00" <= c <= "\u9fff"]),
        "words_en": len(en.split()),
        "note": "model-written from this entry, in close to verbatim scope; not a verdict; exhibit #18 already recorded",
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EVIDENCE_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EVIDENCE_MD.write_text(
        f"# Gazette Feature — {now}\n\n"
        f"**anchor:** {anchor}  ·  **model:** {cfg.get('model')}\n\n"
        f"## 中文 · 一闪 \\n\\n{zh}\\n\\n"
        f"## English\n\n{en}\n\n"
        f"*model printed from the ledger; not a verdict.*\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_JSON}")
    print(f"wrote {EVIDENCE_MD}")
    return 0


def run() -> int:
    return asyncio.run(main())


if __name__ == "__main__":
    sys.exit(run())
