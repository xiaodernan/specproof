"""Per-job LLM cost measurement — real recorded usage from live gateway runs.

Go/No-Go #15 in-repo half: aggregate the token classes recorded in each real
craft report (docs/eval/swebench-logs/<instance>/craft/report.json) and convert
them to a cost estimate with a configurable price table, then compare against
the job's recorded token budget. Writes docs/eval/cost-results.json.

Honesty contract:
- Token counts, calls, timeout retries, iterations and seconds come from REAL
  runs (craft LLMClient stats_report + the job's budget ledger).
- The price table is an EXAMPLE default (DeepSeek public pricing for the
  deepseek-chat tier, USD per 1M tokens); the real llm-api.fagougou.com bill is
  the only source of truth for money. Gate #15 stays PENDING until real bills
  are reconciled and sandbox/DB resource costs are added.
- reasoning_tokens are billed at the completion rate (DeepSeek convention).
- prompt_tokens must equal cache_hit + cache_miss in the recorded shape; the
  script prices the two cache classes and never double-counts the total.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = REPO_ROOT / "docs" / "eval" / "swebench-logs"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "eval" / "cost-results.json"

# Example prices: DeepSeek public pricing for the deepseek-chat tier
# (USD per 1M tokens). Explicitly NOT a claim about the gateway bill.
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


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def job_usage(report: dict[str, Any]) -> dict[str, Any]:
    """Project one craft report onto the usage row (all counts real)."""
    usage = report.get("llm_usage") or {}
    budget = usage.get("budget") or {}
    budget_used = report.get("budget_used") or {}
    cache_hit = _as_int(usage.get("prompt_cache_hit_tokens"))
    cache_miss = _as_int(usage.get("prompt_cache_miss_tokens"))
    prompt_total = _as_int(usage.get("prompt_tokens"))
    if prompt_total <= 0:
        prompt_total = cache_hit + cache_miss
    limit = _as_float(budget.get("limit_tokens"))
    used = _as_float(budget.get("used"))
    return {
        "job_id": str(report.get("job_id") or ""),
        "result": str(report.get("result") or ""),
        "calls": _as_int(usage.get("calls")),
        "timeout_retries": _as_int(usage.get("timeout_retries")),
        "prompt_tokens": prompt_total,
        "prompt_cache_hit_tokens": cache_hit,
        "prompt_cache_miss_tokens": cache_miss,
        "completion_tokens": _as_int(usage.get("completion_tokens")),
        "reasoning_tokens": _as_int(usage.get("reasoning_tokens")),
        "budget_limit_tokens": limit,
        "budget_used_tokens": used,
        "within_token_budget": None if limit <= 0 else used <= limit,
        "iterations": _as_int(budget_used.get("iterations")),
        "seconds": _as_float(budget_used.get("seconds")),
    }


def cost_of(
    usage: dict[str, Any], prices: dict[str, float] | None = None,
) -> dict[str, float]:
    """Token classes -> per-class USD cost (per 1M) + rounded total."""
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
    return {
        "cache_hit_usd": round(hit, 6),
        "cache_miss_usd": round(miss, 6),
        "completion_usd": round(completion, 6),
        "reasoning_usd": round(reasoning, 6),
        "total_usd": round(hit + miss + completion + reasoning, 6),
    }


def collect_reports(reports_dir: Path) -> list[dict[str, Any]]:
    """Load every */craft/report.json under reports_dir (deterministic order)."""
    rows: list[dict[str, Any]] = []
    if not reports_dir.is_dir():
        return rows
    for report_path in sorted(reports_dir.glob("*/craft/report.json")):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict):
            continue
        row = job_usage(report)
        row["source"] = str(report_path.relative_to(reports_dir))
        row.update(cost_of(row))
        rows.append(row)
    return rows


def aggregate(
    rows: list[dict[str, Any]], per_job_budget_usd: float | None,
) -> dict[str, Any]:
    """Cross-job totals; money-budget check only when a budget is supplied."""
    total_usd = round(sum(_as_float(r.get("total_usd")) for r in rows), 6)
    total_tokens = sum(
        _as_int(r.get("prompt_tokens")) + _as_int(r.get("completion_tokens"))
        + _as_int(r.get("reasoning_tokens")) for r in rows
    )
    total_seconds = round(sum(_as_float(r.get("seconds")) for r in rows), 3)
    within_token = sum(1 for r in rows if r.get("within_token_budget") is True)
    checked_token = sum(1 for r in rows if r.get("within_token_budget") is not None)
    agg: dict[str, Any] = {
        "jobs": len(rows),
        "total_usd": total_usd,
        "mean_usd_per_job": round(total_usd / len(rows), 6) if rows else 0.0,
        "total_tokens": total_tokens,
        "total_seconds": total_seconds,
        "jobs_within_token_budget": within_token,
        "jobs_with_token_budget_recorded": checked_token,
    }
    if per_job_budget_usd is not None and per_job_budget_usd > 0:
        within_money = sum(
            1 for r in rows if _as_float(r.get("total_usd")) <= per_job_budget_usd
        )
        agg["per_job_budget_usd"] = per_job_budget_usd
        agg["jobs_within_money_budget"] = within_money
    return agg


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bench_cost",
        description=(
            "按 Job 统计真实 LLM token 用量并换算成本 (Go/No-Go #15 仓库内半程): "
            "读 docs/eval/swebench-logs/*/craft/report.json, 四类 token 按可配置价格表 "
            "折算 USD, 对照每作业已记录 token 预算, 落盘 docs/eval/cost-results.json"
        ),
    )
    parser.add_argument(
        "--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR,
        help="craft report.json 所在日志目录 (默认 docs/eval/swebench-logs)",
    )
    parser.add_argument(
        "--prices-json", type=Path, default=None,
        help="价格表覆盖 JSON (keys: prompt_cache_hit/prompt_cache_miss/completion/reasoning)",
    )
    parser.add_argument(
        "--per-job-budget-usd", type=float, default=None,
        help="每作业货币预算 (USD); 提供时统计预算内作业数, 不提供只做 token 预算对照",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="结果 JSON 路径",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prices: dict[str, float] | None = None
    if args.prices_json is not None:
        try:
            loaded = json.loads(Path(args.prices_json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print("价格表无法读取 (" + str(args.prices_json) + "): " + str(exc))
            return 2
        if not isinstance(loaded, dict):
            print("价格表必须是 JSON 对象")
            return 2
        prices = {str(k): _as_float(v) for k, v in loaded.items()}

    rows = collect_reports(Path(args.reports_dir))
    agg = aggregate(rows, args.per_job_budget_usd)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "prices_used": dict(DEFAULT_PRICES if prices is None else prices),
        "price_note": (
            "示例默认价 = DeepSeek deepseek-chat 公开价 (USD/1M tokens), "
            "非 llm-api.fagougou.com 真实账单; reasoning 按 completion 价折算"
        ),
        "per_job_budget_usd": args.per_job_budget_usd,
        "rows": rows,
        "aggregate": agg,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    for row in rows:
        tokens = row["prompt_tokens"] + row["completion_tokens"] + row["reasoning_tokens"]
        print(
            f"{row['job_id'] or '(unknown)':36s} {row['result']:8s} "
            f"tokens={tokens:7d} cost=${row['total_usd']:.6f} "
            f"budget={row['budget_used_tokens']:.0f}/{row['budget_limit_tokens']:.0f}"
        )
    print(
        f"汇总: jobs={agg['jobs']} total=${agg['total_usd']:.6f} "
        f"mean=${agg['mean_usd_per_job']:.6f}/job "
        f"token预算内={agg['jobs_within_token_budget']}/{agg['jobs_with_token_budget_recorded']}"
    )
    print("结果 JSON: " + str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
