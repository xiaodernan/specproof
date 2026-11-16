#!/usr/bin/env python
"""two_strike_probe — repeat-call prefix-cache behaviour of the live lane.

Fires the exact same minimal request twice back-to-back through the
product's own provider code path and prints the usage objects of both
strikes (was cached_tokens reported? did it climb?).

Never prints api_key material. Cost: two small calls.
"""
import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from providers.base import LLMMessage
from providers.config import load_model_config
from providers.openai_compatible import OpenAICompatibleProvider

cfg = load_model_config()
print(f"source {cfg['source']} | protocol {cfg['protocol']} | model {cfg['model']}", flush=True)

SYSTEM = "铁证优先：任何验证都要可复现。不伪造。不猜测。不泄密。" * 12   # a long-ish prefix, realistic


async def strike(n: int) -> None:
    provider = OpenAICompatibleProvider(
        api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"],
        protocol=cfg["protocol"],
        reasoning_effort=cfg.get("reasoning_effort"),
    )
    resp = await provider.chat(
        [
            LLMMessage(role="system", content=SYSTEM),
            LLMMessage(role="user", content="铁证不伪造。用一句话确认。"),
        ],
        timeout=60.0,
    )
    print(f"strike {n}: model={resp.model} usage={resp.usage}")
    print(f"   reply: {(resp.content or '')[:60]}")


async def main() -> None:
    await strike(1)
    await strike(2)


if __name__ == "__main__":
    asyncio.run(main())
