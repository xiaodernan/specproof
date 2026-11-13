"""Token 级 LLM 用量账本——「缓存健康」面板的持久层。

每次逻辑 LLM 调用在 provider 边界记一行:模型、kind、车道、流式标志、
prompt/completion/cached token 数、耗时、错误标志。**不含 prompt 内容、
不含租户标识、不含业务数据**——红线(§四)继续成立:这份文件可以直接交给
审计方而无需脱敏。

设计纪律与语义缓存同款:

* **尽力而为**——账本写入绝不许弄挂一次模型调用。所有写入有兜底;失败
  计入 ``llm_usage_ledger_errors_total`` 后保持沉默,恰似语义缓存的 50ms
  预算:观测的代价不得转嫁给被观测者。
* **JSONL 追加**——一行一记录,O_APPEND 小块写;api 与 worker 多进程写
  同一本地文件是安全的(小写入原子性假设,与所有单行追加型观测工具同)。
* **轮转**——超过 ``MAX_LEDGER_BYTES`` 重命名为 ``<name>.1``(单代前档,
  原地覆盖),磁盘占用有界;读取端合并主档与前档。
* **聚合是纯函数**——API 路由自己过滤时间窗;本模块只负责读行(容忍撕裂
  行/外来行,坏行跳过绝不抛)。

缓存命中的诚实口径:``cached_tokens`` 只有网关真的上报了才记(没有就缺省
,绝不补零)。命中率 = sum(cached)/sum(prompt),**只对上报了 cached 的调用
子集计算**,并把该子集的调用量一并报告——不知道就说不知道,是这套系统
一贯的诚实边界。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from observability.metrics import incr

#: 轮转阈值。一次调用一条记录 ≈ 200B,8MB ≈ 4 万次调用,足够面板的
#: 时间窗聚合,又不会吃磁盘。
MAX_LEDGER_BYTES = 8 * 1024 * 1024

#: 窗口上限：30 天。更大的窗口只是把磁盘上有限的记录反复聚合。
MAX_WINDOW_HOURS = 24 * 30

#: 单文件锁。跨线程安全(线程锁足矣——同一进程内的并发全在这里);
#: 跨进程靠 O_APPEND 小写原子性。
_WRITE_LOCK = threading.Lock()

#: 记录里允许出现的键——多一个键都算账本schema漂移,宁缺勿滥。
_RECORD_KEYS = (
    "ts",
    "model",
    "kind",
    "lane",
    "streamed",
    "prompt_tokens",
    "completion_tokens",
    "cached_tokens",
    "duration_ms",
    "error",
)


def repo_root() -> Path:
    """仓库根(与 api/data_paths.py 同一算法,但 providers 不 import api)。"""
    return Path(__file__).resolve().parents[1]


def ledger_path() -> Path:
    """账本文件路径:SPECPROOF_LLM_USAGE_LEDGER 显式指定,否则仓库 .local 下。"""
    raw = os.getenv("SPECPROOF_LLM_USAGE_LEDGER", "").strip()
    if raw:
        return Path(raw).expanduser()
    return repo_root() / ".local" / "llm_usage.jsonl"


def record_llm_call(
    *,
    model: str,
    kind: str | None,
    lane: str,
    streamed: bool,
    usage: dict[str, Any] | None,
    duration_ms: int,
    error: bool = False,
) -> bool:
    """Append one call record; returns True when a line actually landed.

    ``usage`` is the parsed usage dict (``_parse_usage`` shape). Token counts
    are read from it verbatim — absent fields stay absent in the record, so
    the aggregate layer can distinguish "gateway reported no cache data"
    from "zero cache hits", which the honesty rules require.
    """
    usage = usage or {}
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": str(model or ""),
        "kind": str(kind) if kind else None,
        "lane": str(lane),
        "streamed": bool(streamed),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": usage.get("prompt_cache_hit_tokens"),
        "duration_ms": int(duration_ms),
        "error": bool(error),
    }
    # 网关没上报的字段就从记录里缺席——"没报"与"零命中"在记录层就分开,
    # 聚合层才能诚实区分两者(红线:绝不捏造零值)。
    for token_key in ("prompt_tokens", "completion_tokens", "cached_tokens"):
        if record[token_key] is None:
            del record[token_key]
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    path = ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK:
            _rotate_if_needed(path)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError:
        incr("llm_usage_ledger_errors_total")
        return False
    return True


def _rotate_if_needed(path: Path) -> None:
    """Single-generation rotation: main -> .1 (overwrite), bounded disk."""
    try:
        if path.exists() and path.stat().st_size >= MAX_LEDGER_BYTES:
            path.replace(path.with_name(path.name + ".1"))
    except OSError:
        # Rotation is an optimisation, not a correctness step; the append
        # below still works either way.
        pass


def read_records(path: Path | None = None) -> list[dict[str, Any]]:
    """Parse every well-formed record from main + previous generation.

    Torn lines (a crashed writer), foreign content and empty lines are
    skipped without raising — an observability ledger that throws on its
    own history is worse than one that silently shrinks it.
    """
    base = path if path is not None else ledger_path()
    records: list[dict[str, Any]] = []
    candidates = (base.with_name(base.name + ".1"), base)
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(parsed, dict):
                        continue
                    if not any(key in parsed for key in _RECORD_KEYS):
                        continue
                    records.append(parsed)
        except OSError:
            continue
    return records


def _parse_ts(value: Any) -> float | None:
    """ISO-8601 (with or without offset) -> epoch seconds; None when hopeless."""
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def summarize(
    records: list[dict[str, Any]],
    *,
    window_hours: float,
    now: float | None = None,
) -> dict[str, Any]:
    """Aggregate records over the window into the panel's payload.

    Honesty rules the panel inherits:

    * ``hit_rate`` is computed ONLY over calls whose gateway actually
      reported a cached-token figure (``hit_basis_calls`` tells how many);
      calls without the figure neither inflate nor deflate the rate;
    * error calls count in ``calls``/``errors`` but contribute no tokens;
    * latency percentiles come from recorded durations only.
    """
    now_ts = now if now is not None else time.time()
    cutoff = now_ts - window_hours * 3600.0
    window: list[dict[str, Any]] = []
    for record in records:
        ts = _parse_ts(record.get("ts"))
        if ts is None or ts < cutoff or ts > now_ts + 60.0:
            continue
        window.append(record)

    calls = len(window)
    errors = sum(1 for r in window if r.get("error") is True)
    streamed = sum(1 for r in window if r.get("streamed") is True)

    prompt = 0
    completion = 0
    cached = 0
    prompt_reported = 0  # prompt_tokens summed ONLY over cached-reported calls
    hit_basis_calls = 0
    durations: list[int] = []
    by_kind: dict[str, dict[str, Any]] = {}
    for record in window:
        if record.get("error") is True:
            continue
        kind = str(record.get("kind") or "(untyped)")
        bucket = by_kind.setdefault(
            kind,
            {"kind": kind, "calls": 0, "prompt_tokens": 0, "cached_tokens": 0,
             "cached_reported": 0, "prompt_reported": 0},
        )
        bucket["calls"] += 1
        p = record.get("prompt_tokens")
        if isinstance(p, (int, float)) and p >= 0:
            prompt += int(p)
            bucket["prompt_tokens"] += int(p)
        c = record.get("completion_tokens")
        if isinstance(c, (int, float)) and c >= 0:
            completion += int(c)
        cached_value = record.get("cached_tokens")
        if isinstance(cached_value, (int, float)) and cached_value >= 0:
            cached += int(cached_value)
            bucket["cached_tokens"] += int(cached_value)
            hit_basis_calls += 1
            bucket["cached_reported"] += 1
            if p is not None:
                prompt_reported += int(p)
                bucket["prompt_reported"] += int(p)
        d = record.get("duration_ms")
        if isinstance(d, (int, float)) and d >= 0:
            durations.append(int(d))

    for bucket in by_kind.values():
        bucket["hit_rate"] = (
            None if bucket["cached_reported"] == 0
            else _rate(bucket["cached_tokens"], bucket["prompt_reported"])
        )
        bucket.pop("cached_reported")
        bucket.pop("prompt_reported")

    def percentile(sorted_values: list[int], fraction: float) -> int | None:
        if not sorted_values:
            return None
        index = min(len(sorted_values) - 1, max(0, round(fraction * (len(sorted_values) - 1))))
        return sorted_values[index]

    durations.sort()
    latency_p50 = percentile(durations, 0.50)
    latency_p95 = percentile(durations, 0.95)

    # Hourly trend buckets (UTC), oldest first: calls + cache share per hour.
    trend: list[dict[str, Any]] = []
    if window:
        bucket_hours: dict[int, dict[str, Any]] = {}
        for record in window:
            if record.get("error") is True:
                continue  # errors count in calls/errors of the roll-up, not here
            ts = _parse_ts(record.get("ts"))
            if ts is None:
                continue
            hour = int(ts // 3600)
            bucket = bucket_hours.setdefault(
                hour,
                {"hour": hour, "calls": 0, "prompt_tokens": 0, "cached_tokens": 0,
                 "prompt_reported": 0},
            )
            bucket["calls"] += 1
            p = record.get("prompt_tokens")
            if isinstance(p, (int, float)) and p >= 0:
                bucket["prompt_tokens"] += int(p)
            cached_value = record.get("cached_tokens")
            if isinstance(cached_value, (int, float)) and cached_value >= 0:
                bucket["cached_tokens"] += int(cached_value)
                if p is not None:
                    bucket["prompt_reported"] += int(p)
        for hour in sorted(bucket_hours):
            bucket = bucket_hours[hour]
            bucket_start = datetime.fromtimestamp(hour * 3600, tz=timezone.utc)
            trend.append({
                "bucket_start": bucket_start.isoformat(timespec="seconds"),
                "calls": bucket["calls"],
                "prompt_tokens": bucket["prompt_tokens"],
                "cached_tokens": bucket["cached_tokens"],
                "hit_rate": (
                    None if bucket["prompt_reported"] == 0
                    else _rate(bucket["cached_tokens"], bucket["prompt_reported"])
                ),
            })

    return {
        "window_hours": window_hours,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "calls": calls,
        "errors": errors,
        "error_rate": _rate(errors, calls),
        "streamed_ratio": _rate(streamed, calls),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cached_tokens": cached,
        "hit_rate": _rate(cached, prompt_reported),
        "hit_basis_calls": hit_basis_calls,
        "latency_p50_ms": latency_p50,
        "latency_p95_ms": latency_p95,
        "by_kind": sorted(by_kind.values(), key=lambda b: -b["calls"]),
        "trend": trend,
    }


def summary(window_hours: float = 24.0) -> dict[str, Any]:
    """One-shot read+aggregate for the API route."""
    window_hours = max(1.0, min(window_hours, MAX_WINDOW_HOURS))
    return summarize(read_records(), window_hours=window_hours)
