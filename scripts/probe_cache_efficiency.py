"""Cache-efficiency probe against the live wkapi.pro / gpt-6-sol gateway.

Two variants of the `_JUNIT_GENERATION_PROMPT` (imported verbatim from the
codebase) are sent through the SAME production configuration used in real
runs: `OpenAICompatibleProvider` + `stream=True` + `include_usage=True`.

Probe sequence:
  A1  cold  (suffix=AUTH)        — expect cold usage, hit_rate null
  A2  repeat (same bytes)        — expect either cached=42xx or null (gateway-dependent)
  B1  replay with SQL suffix    — expect prefix cache hit ≈ stable prefix length
  A3  replay AUTH                — lets you see if same-bytes caching ever kicks in
  B2  repeat SQL                 — reproducibility of B1
  C1  different suffix, same stable prefix — expect stable prefix hit
  B3  third SQL replay           — triplicate reproducibility

Usage:
  python scripts/probe_cache_efficiency.py

Nothing is asserted: this is an *observational* probe, meant to document
what the gateway currently does. Do not wire this into CI — wkapi responses
are not contractual and the cache behavior can change at any time.
"""

import asyncio
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent.nodes.generate_counterexamples import _JUNIT_GENERATION_PROMPT
from providers.base import LLMMessage
from providers.openai_compatible import OpenAICompatibleProvider

SUFFIXES = {
    "AUTH": (
        "ADDITIONAL CONTEXT\nChanged symbols: changeEmail\nRequirement: 非管理员修改邮箱应被拒绝，管理员可以修改\nFindings:\n"
        "- id: FINDING-AUTH-01\n  severity: BLOCKER\n  evidence_type: base_pass_head_fail\n  description: @PreAuthorize removed from changeEmail\nContracts:\n"
        "- id: AUTH-01\n  checker_type: http\n  requirement: 非管理员修改邮箱应被拒绝"
    ),
    "SQL": (
        "ADDITIONAL CONTEXT\nChanged symbols: OrderService.save, OrderRepository\nRequirement: 不信任的输入不得进入 SQL 查询\nFindings:\n"
        "- id: FINDING-SQL-02\n  severity: MAJOR\n  evidence_type: static_regex_analysis\n  description: string concatenation in raw SQL\nContracts:\n"
        "- id: SQL-01\n  checker_type: sql\n  requirement: 输入不得拼接进 SQL"
    ),
    "REDACT": (
        "ADDITIONAL CONTEXT\nChanged symbols: RedactionService.redactEmail\nRequirement: 客户邮箱不得在日志中以明文出现\nFindings:\n"
        "- id: FINDING-REDACT-03\n  severity: MINOR\n  evidence_type: static_regex_analysis\n  description: email logged without redaction\nContracts:\n"
        "- id: REDACT-01\n  checker_type: sql\n  requirement: 邮箱不得以明文进入日志"
    ),
}


async def call(provider: OpenAICompatibleProvider, label: str, prompt: str) -> dict:
    started = time.perf_counter()
    try:
        resp = await provider.chat(messages=[LLMMessage(role="user", content=prompt)], timeout=180.0)
        elapsed = time.perf_counter() - started
        u = resp.usage or {}
        cached = u.get("prompt_cache_hit_tokens")
        prompt_tokens = u.get("prompt_tokens") or 0
        hit_rate = (cached or 0) / prompt_tokens if prompt_tokens else None
        return {
            "label": label,
            "ok": True,
            "elapsed_s": round(elapsed, 2),
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached,
            "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
            "finish_reason": resp.finish_reason,
        }
    except Exception as exc:
        return {"label": label, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}


async def main() -> None:
    provider = OpenAICompatibleProvider()
    print("model:", provider.model, "| base:", provider.base_url)
    sequence = [
        ("A1 cold  AUTH", SUFFIXES["AUTH"]),
        ("A2 same-bytes AUTH", SUFFIXES["AUTH"]),
        ("B1 diff  SQL", SUFFIXES["SQL"]),
        ("A3 replay AUTH", SUFFIXES["AUTH"]),
        ("B2 repeat SQL", SUFFIXES["SQL"]),
        ("C1 diff  REDACT", SUFFIXES["REDACT"]),
        ("B3 third SQL", SUFFIXES["SQL"]),
    ]
    for label, suffix in sequence:
        prompt = _JUNIT_GENERATION_PROMPT + "\n\n" + suffix
        r = await call(provider, label, prompt)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
