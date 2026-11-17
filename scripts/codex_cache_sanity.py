"""Raw sanity strike for the codex lane: two identical pings, same sticky key.

This is NOT a product verdict. It measures the gateway's behavior with a
byte-identical ~400 KB codex prefix + one tiny question, twice, and reports
whether the second call hit the prefix cache.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api.system_codex import codex_first
from api.system_covenant import covenant_prefix
from providers.base import LLMMessage
from providers.config import load_model_config
from providers.openai_compatible import OpenAICompatibleProvider


async def main() -> int:
    cfg = load_model_config()
    provider = OpenAICompatibleProvider(
        api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"],
        protocol=cfg.get("protocol", "responses"),
        reasoning_effort=cfg.get("reasoning_effort"),
    )
    messages = codex_first(covenant_prefix([
        LLMMessage(role="system", content="You are a cache probe. Answer with exactly one word."),
        LLMMessage(role="user", content="ping"),
    ]), "en")
    prefix_chars = sum(len(m.content or "") for m in messages)
    print(f"prefix chars: {prefix_chars} (~{prefix_chars // 4} tokens)")
    try:
        for i in (1, 2):
            started = datetime.now(UTC)
            resp = await asyncio.wait_for(
                provider.chat(
                    messages,
                    timeout=240.0,
                    opts={"reasoning_effort": "low", "prompt_cache_key": "specproof-probe-sanity"},
                ),
                timeout=250.0,
            )
            usage = resp.usage or {}
            elapsed = (datetime.now(UTC) - started).total_seconds()
            print(json.dumps({
                "strike": i,
                "elapsed_s": round(elapsed, 2),
                "content": (resp.content or "").strip()[:80],
                "usage": usage,
            }, ensure_ascii=False))
    finally:
        await provider.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
