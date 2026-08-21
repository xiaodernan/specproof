"""Offline tests for scripts/bench_cost.py (Go/No-Go #15 in-repo measurement).

No network, no LLM, no Docker — fabricated report dicts only; the real
measurement runs against docs/eval/swebench-logs/*/craft/report.json.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

# scripts/ is shadowed by an unrelated site-packages package named "scripts",
# so the script under test is loaded by file path (no sys.path games).
REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "bench_cost", REPO_ROOT / "scripts" / "bench_cost.py",
)
assert _SPEC is not None and _SPEC.loader is not None
bench_cost = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bench_cost)

DEFAULT_PRICES = bench_cost.DEFAULT_PRICES
aggregate = bench_cost.aggregate
collect_reports = bench_cost.collect_reports
cost_of = bench_cost.cost_of
job_usage = bench_cost.job_usage
main = bench_cost.main


def _fake_report(
    *,
    job_id: str = "job-1",
    result: str = "DONE",
    calls: int = 3,
    prompt_tokens: int = 3000,
    cache_hit: int = 1200,
    cache_miss: int = 1800,
    completion_tokens: int = 2000,
    reasoning_tokens: int = 1500,
    limit_tokens: float = 50000.0,
    used_tokens: float = 8000.0,
    iterations: int = 2,
    seconds: float = 120.0,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "result": result,
        "llm_usage": {
            "calls": calls,
            "prompt_tokens": prompt_tokens,
            "prompt_cache_hit_tokens": cache_hit,
            "prompt_cache_miss_tokens": cache_miss,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "budget": {"limit_tokens": limit_tokens, "used": used_tokens},
        },
        "budget_used": {"iterations": iterations, "seconds": seconds},
    }


class TestCostOf:
    def test_math_with_default_prices(self) -> None:
        usage = {
            "prompt_cache_hit_tokens": 1_000_000,
            "prompt_cache_miss_tokens": 1_000_000,
            "completion_tokens": 2_000_000,
            "reasoning_tokens": 3_000_000,
        }
        cost = cost_of(usage)
        assert cost["cache_hit_usd"] == 0.07
        assert cost["cache_miss_usd"] == 0.27
        assert cost["completion_usd"] == 2.20
        assert cost["reasoning_usd"] == 3.30
        assert cost["total_usd"] == 5.84

    def test_price_override(self) -> None:
        usage = {"completion_tokens": 1_000_000}
        cost = cost_of(usage, {"completion": 2.5})
        assert cost["total_usd"] == 2.5
        assert DEFAULT_PRICES["completion"] == 1.10  # default untouched

    def test_duck_defaults(self) -> None:
        cost = cost_of({})
        assert cost["total_usd"] == 0.0


class TestJobUsage:
    def test_projects_real_shape(self) -> None:
        row = job_usage(_fake_report())
        assert row["job_id"] == "job-1"
        assert row["calls"] == 3
        assert row["prompt_tokens"] == 3000
        assert row["prompt_cache_hit_tokens"] == 1200
        assert row["prompt_cache_miss_tokens"] == 1800
        assert row["completion_tokens"] == 2000
        assert row["reasoning_tokens"] == 1500
        assert row["budget_limit_tokens"] == 50000.0
        assert row["budget_used_tokens"] == 8000.0
        assert row["within_token_budget"] is True
        assert row["iterations"] == 2
        assert row["seconds"] == 120.0

    def test_over_budget_is_false(self) -> None:
        row = job_usage(_fake_report(used_tokens=99999.0))
        assert row["within_token_budget"] is False

    def test_no_budget_limit_is_none(self) -> None:
        row = job_usage(_fake_report(limit_tokens=0.0))
        assert row["within_token_budget"] is None

    def test_prompt_falls_back_to_cache_sum(self) -> None:
        row = job_usage(_fake_report(prompt_tokens=0, cache_hit=700, cache_miss=300))
        assert row["prompt_tokens"] == 1000

    def test_empty_report_duck_defaults(self) -> None:
        row = job_usage({})
        assert row["calls"] == 0
        assert row["within_token_budget"] is None


class TestCollectAndAggregate:
    def _write_report(self, base: Path, name: str, report: dict[str, Any]) -> Path:
        craft_dir = base / name / "craft"
        craft_dir.mkdir(parents=True)
        path = craft_dir / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_collect_reports_sorted_and_priced(self, tmp_path: Path) -> None:
        self._write_report(tmp_path, "b", _fake_report(job_id="job-b"))
        self._write_report(tmp_path, "a", _fake_report(job_id="job-a"))
        rows = collect_reports(tmp_path)
        assert [r["job_id"] for r in rows] == ["job-a", "job-b"]
        assert rows[0]["source"] == str(Path("a") / "craft" / "report.json")
        assert rows[0]["total_usd"] > 0

    def test_skips_broken_json(self, tmp_path: Path) -> None:
        self._write_report(tmp_path, "a", _fake_report(job_id="job-a"))
        craft_dir = tmp_path / "broken" / "craft"
        craft_dir.mkdir(parents=True)
        (craft_dir / "report.json").write_text("{not json", encoding="utf-8")
        rows = collect_reports(tmp_path)
        assert [r["job_id"] for r in rows] == ["job-a"]

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        assert collect_reports(tmp_path / "nope") == []

    def test_aggregate(self) -> None:
        rows = [
            job_usage(_fake_report(job_id="j1", used_tokens=1000.0)),
            job_usage(_fake_report(job_id="j2", used_tokens=90000.0)),
        ]
        for row in rows:
            row.update(cost_of(row))
        agg = aggregate(rows, None)
        assert agg["jobs"] == 2
        assert agg["jobs_within_token_budget"] == 1
        assert agg["jobs_with_token_budget_recorded"] == 2
        assert agg["total_usd"] == round(rows[0]["total_usd"] + rows[1]["total_usd"], 6)
        assert "per_job_budget_usd" not in agg

    def test_aggregate_money_budget(self) -> None:
        rows = [
            job_usage(_fake_report(job_id="j1", used_tokens=1000.0)),
            job_usage(_fake_report(
                job_id="j2", used_tokens=90000.0, prompt_tokens=30000,
                cache_hit=12000, cache_miss=18000, completion_tokens=20000,
                reasoning_tokens=15000,
            )),
        ]
        for row in rows:
            row.update(cost_of(row))
        agg = aggregate(rows, per_job_budget_usd=0.01)
        assert agg["per_job_budget_usd"] == 0.01
        assert agg["jobs_within_money_budget"] == 1


class TestMain:
    def _write_report(self, base: Path, report: dict[str, Any]) -> None:
        craft_dir = base / "case" / "craft"
        craft_dir.mkdir(parents=True)
        (craft_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

    def test_end_to_end_writes_output(self, tmp_path: Path, capsys: Any) -> None:
        self._write_report(tmp_path, _fake_report(job_id="job-1"))
        out = tmp_path / "cost-results.json"
        code = main([
            "--reports-dir", str(tmp_path),
            "--per-job-budget-usd", "1.0",
            "--output", str(out),
        ])
        assert code == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["prices_used"] == DEFAULT_PRICES
        assert payload["rows"][0]["job_id"] == "job-1"
        assert payload["aggregate"]["jobs"] == 1
        assert payload["aggregate"]["per_job_budget_usd"] == 1.0
        captured = capsys.readouterr().out
        assert "汇总: jobs=1" in captured

    def test_missing_dir_still_writes_empty(self, tmp_path: Path) -> None:
        out = tmp_path / "cost-results.json"
        code = main(["--reports-dir", str(tmp_path / "nope"), "--output", str(out)])
        assert code == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["aggregate"]["jobs"] == 0
        assert payload["rows"] == []
