#!/usr/bin/env python
"""LLM cache probe — what does the configured provider actually report?

Reads the model config through providers.config (the reader every other LLM
consumer uses); never prints or writes the API key. Measures prompt /
completion / cached tokens on non-stream and stream+include_usage lanes for
short and long prompts. The point is observation, not optimization:
wkapi's cached_tokens is dominated by its static ~4k-token prefix and is NOT
the user's message hit rate. Do not read this script's output as an SLA.

Usage:
    python scripts/llm_cache_probe.py
"""

import asyncio
import io
import sys

from providers.config import load_model_config
from providers.responses_protocol import normalize_base_url
from openai import AsyncOpenAI

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

cfg = load_model_config()
print(f"config source: {cfg['source']}  model: {cfg['model']}  base_url: {cfg['base_url']}")

client = AsyncOpenAI(
    api_key=cfg["api_key"],
    base_url=normalize_base_url(cfg["base_url"]),
    max_retries=1,
    timeout=60.0,
)

LONG_BODY = "SpecProof 的证据体系以差分执行为锚：base_pass_head_fail 是一等铁证。" * 90
SHORT_Q = "只回答一个字：证。"


def cached_of(usage) -> "int | None":
    details = getattr(usage, "prompt_tokens_details", None) if usage else None
    return getattr(details, "cached_tokens", None) if details else None


async def nonstream(label, prompt) -> None:
    try:
        r = await client.chat.completions.create(
            model=cfg["model"], temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        u = r.usage
        print(f"{label:32} non-stream  prompt={u.prompt_tokens} completion={u.completion_tokens} cached={cached_of(u)}")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:32} non-stream  FAILED: {exc}")


async def stream(label, prompt) -> None:
    try:
        r = await client.chat.completions.create(
            model=cfg["model"], temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            stream=True, stream_options={"include_usage": True},
        )
        usage = None
        async for chunk in r:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
        print(f"{label:32} stream+incl  prompt={usage.prompt_tokens if usage else '?'} "
              f"completion={usage.completion_tokens if usage else '?'} cached={cached_of(usage)}")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:32} stream+incl  FAILED: {exc}")


async def main() -> None:
    await nonstream("short prompt", SHORT_Q)
    await stream("short prompt", SHORT_Q)
    await nonstream("long prompt (~4.5k tok zh)", LONG_BODY)
    await stream("long prompt (~4.5k tok zh)", LONG_BODY)
    await nonstream("long prompt again", LONG_BODY)
    await stream("long prompt again", LONG_BODY)


if __name__ == "__main__":
    asyncio.run(main())
