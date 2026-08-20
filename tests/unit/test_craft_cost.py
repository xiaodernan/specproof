"""Unit tests for the craft cost function (§14 成本函数)."""

from __future__ import annotations

from craft.cost import DEFAULT_PRICES, attach_cost, cost_of_usage

_USAGE = {
    "prompt_cache_hit_tokens": 6784,
    "prompt_cache_miss_tokens": 3402,
    "completion_tokens": 21664,
    "reasoning_tokens": 20885,
    "prompt_tokens": 10186,
}


def test_cost_of_usage_math() -> None:
    cost = cost_of_usage(_USAGE)
    assert cost["total_usd"] == round(
        (6784 * 0.07 + 3402 * 0.27 + 21664 * 1.10 + 20885 * 1.10)
        / 1_000_000,
        6,
    )
    assert cost["cache_hit_usd"] >= 0
    assert cost["reasoning_usd"] == round(20885 * 1.10 / 1_000_000, 6)


def test_custom_prices_override() -> None:
    cost = cost_of_usage(_USAGE, prices={
        "prompt_cache_hit": 0.0,
        "prompt_cache_miss": 0.0,
        "completion": 1.0,
        "reasoning": 1.0,
    })
    assert cost["cache_hit_usd"] == 0.0
    assert cost["cache_miss_usd"] == 0.0


def test_empty_usage_is_zero() -> None:
    cost = cost_of_usage({})
    assert cost["total_usd"] == 0.0


def test_attach_cost_adds_key_when_usage_present() -> None:
    report = {"llm_usage": _USAGE, "result": "DONE"}
    attach_cost(report)
    assert report["cost_usd"]["total_usd"] > 0
    assert report["result"] == "DONE"


def test_attach_cost_noop_without_usage() -> None:
    report = {"result": "DONE"}
    attach_cost(report)
    assert "cost_usd" not in report


def test_default_prices_documented_example() -> None:
    assert set(DEFAULT_PRICES) == {
        "prompt_cache_hit", "prompt_cache_miss", "completion", "reasoning",
    }
