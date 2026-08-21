"""Craft cost function (§14 成本函数).

Converts the recorded per-class token usage (craft/llm.py stats_report)
into a USD estimate with an explicit price table. The default table is the
DeepSeek public deepseek-chat tier (USD per 1M tokens) — an EXAMPLE, not a
claim about any real gateway bill (same honesty contract as
scripts/bench_cost.py: the real bill is the only money source of truth).
reasoning tokens are priced at the completion rate (DeepSeek convention);
prompt tokens are split into cache hit/miss classes and never double-counted.
"""
from __future__ import annotations

from typing import Any

DEFAULT_PRICES: dict[str, float] = {
    "prompt_cache_hit": 0.07,
    "prompt_cache_miss": 0.27,
    "completion": 1.10,
    "reasoning": 1.10,
}

_PER_MILLION = 1_000_000.0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def cost_of_usage(
    usage: dict[str, Any], prices: dict[str, float] | None = None,
) -> dict[str, float]:
    """stats_report()-shaped usage → per-class + total USD (6dp)."""
    table = dict(DEFAULT_PRICES if prices is None else prices)
    hit = (
        _as_float(usage.get("prompt_cache_hit_tokens"))
        / _PER_MILLION * table.get("prompt_cache_hit", 0.0)
    )
    miss = (
        _as_float(usage.get("prompt_cache_miss_tokens"))
        / _PER_MILLION * table.get("prompt_cache_miss", 0.0)
    )
    completion = (
        _as_float(usage.get("completion_tokens"))
        / _PER_MILLION * table.get("completion", 0.0)
    )
    reasoning = (
        _as_float(usage.get("reasoning_tokens"))
        / _PER_MILLION * table.get("reasoning", 0.0)
    )
    total = hit + miss + completion + reasoning
    return {
        "cache_hit_usd": round(hit, 6),
        "cache_miss_usd": round(miss, 6),
        "completion_usd": round(completion, 6),
        "reasoning_usd": round(reasoning, 6),
        "total_usd": round(total, 6),
    }


def attach_cost(
    report: dict[str, Any], prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Add report["cost_usd"] from report["llm_usage"] (no-op when absent).

    Callers without recorded usage (deterministic runs) keep the old
    report shape — no cost key is invented for zero LLM work.
    """
    usage = report.get("llm_usage")
    if not usage:
        return report
    report["cost_usd"] = cost_of_usage(usage, prices)
    return report
