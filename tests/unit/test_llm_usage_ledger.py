"""Token 级 LLM 用量账本(#BB5)——写入、诚实聚合、轮转、容错、路由。

四条腿:

* 写入:每次逻辑调用一行;usage 缺席的字段在记录里也缺席(绝不补零),
  这样聚合层能区分"网关没报缓存数据"与"零命中";
* 聚合:hit_rate 只对网关上报了 cached 的调用子集计算,子集大小
  (hit_basis_calls)一并报告——诚实口径;错误调用计入调用量但不出 token;
* 容错:撕裂行/外来行/空行跳过绝不抛;写入失败返回 False 并计数,
  绝不弄挂模型调用;轮转有界(单代前档);
* 路由:GET /api/v1/llm/usage/summary 读账本聚合,require_api_key 保护。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fastapi.testclient import TestClient

from api.server import app
from providers import usage_ledger as ledger
from providers.usage_ledger import (
    read_records,
    record_llm_call,
    summarize,
)

_API_KEY = "test-usage-key"


def _headers() -> dict[str, str]:
    return {"X-API-Key": _API_KEY}


def _rec(ts: str | None = None, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ts": ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": "test-model",
        "kind": "diagnose",
        "lane": "policy",
        "streamed": True,
        "prompt_tokens": 100,
        "completion_tokens": 25,
        "cached_tokens": 80,
        "duration_ms": 1500,
        "error": False,
    }
    base.update(overrides)
    return base


# ── 写入 ──────────────────────────────────────────────────────────────


class TestRecord:
    def test_record_appends_one_line_and_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        assert record_llm_call(
            model="m1", kind="draft", lane="policy", streamed=True,
            usage={"prompt_tokens": 10, "completion_tokens": 2,
                   "prompt_cache_hit_tokens": 8},
            duration_ms=120,
        )
        records = read_records(path if False else None)  # default path via env
        # conftest 把 SPECPROOF_LLM_USAGE_LEDGER 指到 tmp_path——这里读默认路径
        assert len(records) >= 1
        latest = records[-1]
        assert latest["prompt_tokens"] == 10
        assert latest["cached_tokens"] == 8
        assert latest["model"] == "m1"
        assert latest["lane"] == "policy"

    def test_missing_usage_fields_stay_absent_not_zero(self, tmp_path: Path) -> None:
        record_llm_call(
            model="m1", kind=None, lane="direct", streamed=True,
            usage={}, duration_ms=50,
        )
        records = read_records()
        latest = records[-1]
        assert "cached_tokens" not in latest
        assert "prompt_tokens" not in latest
        assert latest["kind"] is None
        assert latest["error"] is False

    def test_error_call_records_no_tokens(self, tmp_path: Path) -> None:
        record_llm_call(
            model="m1", kind="diagnose", lane="direct", streamed=True,
            usage={}, duration_ms=900, error=True,
        )
        latest = read_records()[-1]
        assert latest["error"] is True
        assert "prompt_tokens" not in latest

    def test_write_failure_never_raises(self, tmp_path: Path) -> None:
        # 指到一个"父目录是文件"的路径——mkdir/OSError 必然发生
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir", encoding="utf-8")
        import os as _os
        old = _os.environ.get("SPECPROOF_LLM_USAGE_LEDGER")
        _os.environ["SPECPROOF_LLM_USAGE_LEDGER"] = str(blocker / "inner" / "l.jsonl")
        try:
            assert record_llm_call(
                model="m1", kind=None, lane="direct", streamed=True,
                usage={}, duration_ms=1,
            ) is False
        finally:
            if old is None:
                _os.environ.pop("SPECPROOF_LLM_USAGE_LEDGER", None)
            else:
                _os.environ["SPECPROOF_LLM_USAGE_LEDGER"] = old

    def test_rotation_keeps_previous_generation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = tmp_path / "l.jsonl"
        monkeypatch.setenv("SPECPROOF_LLM_USAGE_LEDGER", str(path))
        old_limit = ledger.MAX_LEDGER_BYTES
        ledger.MAX_LEDGER_BYTES = 10  # 每行都超限 → 每次写都轮转
        try:
            for i in range(3):
                assert record_llm_call(
                    model=f"m{i}", kind=None, lane="direct", streamed=True,
                    usage={"prompt_tokens": 1}, duration_ms=1,
                )
        finally:
            ledger.MAX_LEDGER_BYTES = old_limit
        # 单代轮转:每次超限写都把主档压成 .1(原地覆盖)——极限阈值下只剩
        # 最后两代(m1 在前档, m2 在主档),磁盘有界是设计内行为。
        records = read_records(path)
        assert {r["model"] for r in records} == {"m1", "m2"}
        assert (path.with_name(path.name + ".1")).exists()


# ── 聚合(诚实口径) ────────────────────────────────────────────────────


class TestSummarize:
    def test_hit_rate_only_over_reported_subset(self) -> None:
        records = [
            _rec(cached_tokens=80, prompt_tokens=100),   # 上报: 80/100
            _rec(cached_tokens=None, prompt_tokens=100),  # 未上报: 不进分子分母
        ]
        out = summarize(records, window_hours=24)
        assert out["hit_rate"] == 0.8
        assert out["hit_basis_calls"] == 1
        # token 总量仍包含未上报调用的 prompt(总消耗是真的)
        assert out["prompt_tokens"] == 200

    def test_error_calls_count_but_contribute_no_tokens(self) -> None:
        records = [
            _rec(),
            _rec(error=True, prompt_tokens=None, cached_tokens=None,
                 completion_tokens=None, duration_ms=999),
        ]
        out = summarize(records, window_hours=24)
        assert out["calls"] == 2
        assert out["errors"] == 1
        assert out["error_rate"] == 0.5
        assert out["prompt_tokens"] == 100
        assert out["latency_p50_ms"] == 1500  # 错误调用的耗时也真实计入分位

    def test_window_filters_stale_records(self) -> None:
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat(
            timespec="seconds")
        records = [_rec(), _rec(ts=old_ts, cached_tokens=None)]
        out = summarize(records, window_hours=24)
        assert out["calls"] == 1

    def test_trend_buckets_are_hourly_and_sorted(self) -> None:
        now = time.time()
        hour0 = int(now // 3600) * 3600
        cur = datetime.fromtimestamp(hour0, tz=timezone.utc)
        prev = datetime.fromtimestamp(hour0 - 3600, tz=timezone.utc)
        records = [
            _rec(ts=cur.isoformat(timespec="seconds")),
            _rec(ts=cur.isoformat(timespec="seconds")),
            _rec(ts=prev.isoformat(timespec="seconds"), cached_tokens=None),
        ]
        out = summarize(records, window_hours=24)
        assert [b["calls"] for b in out["trend"]] == [1, 2]
        assert out["trend"][0]["bucket_start"] < out["trend"][1]["bucket_start"]
        assert out["trend"][1]["hit_rate"] == 0.8

    def test_by_kind_breakdown(self) -> None:
        records = [
            _rec(kind="diagnose"),
            _rec(kind="draft", cached_tokens=None),
        ]
        out = summarize(records, window_hours=24)
        kinds = {b["kind"]: b for b in out["by_kind"]}
        assert kinds["diagnose"]["calls"] == 1
        assert kinds["diagnose"]["hit_rate"] == 0.8
        assert kinds["draft"]["hit_rate"] is None

    def test_empty_window_is_all_none_not_fabricated(self) -> None:
        out = summarize([], window_hours=24)
        assert out["calls"] == 0
        assert out["hit_rate"] is None
        assert out["latency_p95_ms"] is None
        assert out["trend"] == []


# ── 容错读取 ──────────────────────────────────────────────────────────


class TestReadTolerance:
    def test_torn_and_foreign_lines_are_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "l.jsonl"
        good = json.dumps(_rec(), ensure_ascii=False)
        path.write_text(
            good + "\n" + '{"ts": "torn' + "\n" + "not json at all\n\n"
            + json.dumps([1, 2, 3]) + "\n" + good + "\n",
            encoding="utf-8",
        )
        records = read_records(path)
        assert len(records) == 2

    def test_missing_file_is_empty_not_error(self, tmp_path: Path) -> None:
        assert read_records(tmp_path / "nope.jsonl") == []


# ── 路由 ──────────────────────────────────────────────────────────────


@pytest.fixture()
def seeded_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "route_ledger.jsonl"
    monkeypatch.setenv("SPECPROOF_LLM_USAGE_LEDGER", str(path))
    monkeypatch.setenv("SPECPROOF_API_KEY", _API_KEY)
    for i in range(3):
        record_llm_call(
            model="gpt-6-sol", kind="diagnose", lane="policy", streamed=True,
            usage={"prompt_tokens": 1000, "completion_tokens": 100,
                   "prompt_cache_hit_tokens": 950},
            duration_ms=2000 + i,
        )
    return path


class TestRoute:
    def test_summary_endpoint_aggregates_seeded_ledger(
        self, seeded_ledger: Path,
    ) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/v1/llm/usage/summary?window_hours=24",
                              headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["calls"] == 3
        assert body["hit_rate"] == 0.95
        assert body["hit_basis_calls"] == 3
        assert body["prompt_tokens"] == 3000
        assert body["latency_p50_ms"] == 2001
        assert body["streamed_ratio"] == 1.0
        assert body["by_kind"][0]["kind"] == "diagnose"
        assert len(body["trend"]) == 1

    def test_summary_requires_api_key(self, seeded_ledger: Path) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/v1/llm/usage/summary")
        assert resp.status_code in (401, 403)

    def test_summary_window_is_clamped(self, seeded_ledger: Path) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/v1/llm/usage/summary?window_hours=999999",
                              headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["window_hours"] == ledger.MAX_WINDOW_HOURS

    def test_window_must_be_positive(self, seeded_ledger: Path) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/v1/llm/usage/summary?window_hours=0",
                              headers=_headers())
        assert resp.status_code == 422
