#!/usr/bin/env python
"""Semantic cache bench — prove the policy cache engages for cacheable kinds.

Reads the model config through providers.config (the reader every other LLM
consumer uses; the API key is never printed or written). Forces the
policy gate (SPECPROOF_PROVIDER_POLICY=1), then:

* calls with kind="draft" TWICE, identical prompt (expect: second call is a
  cache replay — near-zero latency, policy cache hits 0 → 1, network called once);
* calls with kind="court" TWICE, identical prompt (evidence kind — expect:
  cache bypassed by construction, hits unchanged, both calls hit the network).

The point is measurement, not advocacy. Verdicts are the repo's own logic:
draft|diagnose cache, evidence kinds never. Cost: 4 small completions.

Usage:
    python scripts/semantic_cache_bench.py
"""

import asyncio
import io
import os
import sys
import time

os.environ.setdefault("SPECPROOF_PROVIDER_POLICY", "1")

from providers.base import LLMMessage  # noqa: E402
from providers.config import load_model_config  # noqa: E402
from providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROMPT = "Reply with exactly: OK"  # minimal, deterministic, near-zero tokens


def usage_total(resp) -> "int | None":
    u = getattr(resp, "usage", None)
    if isinstance(u, dict):
        return u.get("total_tokens")
    return getattr(u, "total_tokens", None)


async def main() -> None:
    cfg = load_model_config()
    print(f"config source: {cfg['source']}  model: {cfg['model']}")
    provider = OpenAICompatibleProvider(
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"], probe_on_init=False
    )
    policy = getattr(provider, "_policy", None)
    print(f"policy engaged: {policy is not None}")

    async def call(kind: str):
        t0 = time.perf_counter()
        try:
            resp = await provider.chat(
                messages=[LLMMessage(role="user", content=PROMPT)],
                timeout=90.0,
                kind=kind,
            )
            return resp, (time.perf_counter() - t0) * 1000, None
        except Exception as exc:  # noqa: BLE001
            return None, (time.perf_counter() - t0) * 1000, f"{type(exc).__name__}: {exc}"

    async def pair(kind: str) -> None:
        hits0 = policy.cache.stats()["hits"] if policy is not None else 0
        puts0 = policy.cache.stats()["puts"] if policy is not None else 0
        r1, t1, e1 = await call(kind)
        r2, t2, e2 = await call(kind)
        hits1 = policy.cache.stats()["hits"] if policy is not None else 0
        puts1 = policy.cache.stats()["puts"] if policy is not None else 0
        print(f"\nkind={kind}")
        print(f"  call 1: {t1:8.1f} ms  total_tokens={usage_total(r1) if r1 else 'ERR'}  err={e1}")
        print(f"  call 2: {t2:8.1f} ms  total_tokens={usage_total(r2) if r2 else 'ERR'}  err={e2}")
        print(f"  cache: hits {hits0} -> {hits1}   puts {puts0} -> {puts1}")
        if r1 and r2:
            same = (getattr(r1, "content", "") or "").strip() == (getattr(r2, "content", "") or "").strip()
            print(f"  replay identical content: {same}")

    await pair("draft")   # cacheable: expect second call = cache replay
    await pair("court")   # evidence kind: expect cache bypassed both times
    if policy is not None:
        print("\nfinal cache stats:", policy.cache.stats())


if __name__ == "__main__":
    asyncio.run(main())
