"""Unit tests for scripts/bench_latency.py.

The script computes per-case-class p50/p95/mean latency statistics from
`specproof eval` results JSONs and renders a markdown summary. These
tests exercise the statistics on synthetic data and prove that missing
or unusable durations are counted honestly - excluded from the numbers
rather than coerced or fabricated.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bench_latency.py"


def _load_bench() -> Any:
    """Load scripts/bench_latency.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("bench_latency", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bench() -> Any:
    """The bench_latency module under test."""
    return _load_bench()


def test_p50_median_correctness(bench: Any) -> None:
    assert bench.p50([1.0, 2.0, 3.0]) == 2.0
    assert bench.p50([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert bench.p50([7.0]) == 7.0
    assert bench.p50([]) is None


def test_p95_linear_interpolation(bench: Any) -> None:
    assert bench.p95([1.0, 2.0, 3.0, 4.0]) == pytest.approx(3.85)
    values = [float(i) for i in range(1, 21)]
    assert bench.p95(values) == pytest.approx(19.05)
    assert bench.percentile(values, 100.0) == 20.0
    assert bench.percentile(values, 0.0) == 1.0


def test_mean_correctness(bench: Any) -> None:
    assert bench.mean([2.0, 4.0, 6.0]) == 4.0
    assert bench.mean([5.0]) == 5.0
    assert bench.mean([]) is None


def test_percentile_rejects_out_of_range(bench: Any) -> None:
    with pytest.raises(ValueError):
        bench.percentile([1.0, 2.0], -1.0)
    with pytest.raises(ValueError):
        bench.percentile([1.0, 2.0], 101.0)


def test_missing_and_unusable_durations_excluded_and_counted(bench: Any) -> None:
    cases: list[dict[str, Any]] = [
        {"case": "ok", "should_detect": True, "duration_ms": 10},
        {"case": "no-field", "should_detect": True},
        {"case": "null", "should_detect": True, "duration_ms": None},
        {"case": "string", "should_detect": True, "duration_ms": "12"},
        {"case": "negative", "should_detect": True, "duration_ms": -5},
        {"case": "bool", "should_detect": True, "duration_ms": True},
        {"case": "nan", "should_detect": True, "duration_ms": float("nan")},
        {"case": "negative-class", "should_detect": False, "duration_ms": 20},
    ]
    durations, missing = bench.collect_durations(cases, True)
    assert durations == [10.0]
    assert missing == 6

    row = bench.class_stats(cases, "should-detect", True)
    assert row["cases"] == 7
    assert row["timed"] == 1
    assert row["missing"] == 6
    assert row["mean_ms"] == 10.0
    assert row["p50_ms"] == 10.0
    assert row["p95_ms"] == 10.0
    assert row["min_ms"] == 10.0
    assert row["max_ms"] == 10.0


def test_aggregate_stats_rows_and_buckets(bench: Any) -> None:
    cases: list[dict[str, Any]] = [
        {"case": "p1", "should_detect": True, "duration_ms": 10},
        {"case": "p2", "should_detect": True, "duration_ms": 30},
        {"case": "n1", "should_detect": False, "duration_ms": 100},
        {"case": "n2", "should_detect": False},
    ]
    rows = bench.aggregate_stats(cases)
    by_class = {row["class"]: row for row in rows}

    positive = by_class["should-detect"]
    assert positive["cases"] == 2
    assert positive["timed"] == 2
    assert positive["missing"] == 0
    assert positive["mean_ms"] == 20.0
    assert positive["p50_ms"] == 20.0

    negative = by_class["negative"]
    assert negative["cases"] == 2
    assert negative["timed"] == 1
    assert negative["missing"] == 1
    assert negative["mean_ms"] == 100.0

    overall = by_class["all"]
    assert overall["cases"] == 4
    assert overall["timed"] == 3
    assert overall["missing"] == 1
    assert overall["mean_ms"] == pytest.approx((10 + 30 + 100) / 3)
    assert overall["p50_ms"] == 30.0
    assert overall["p95_ms"] == pytest.approx(93.0)


def test_empty_input_yields_none_stats_and_honest_note(bench: Any) -> None:
    rows = bench.aggregate_stats([])
    assert len(rows) == 3
    for row in rows:
        assert row["cases"] == 0
        assert row["timed"] == 0
        assert row["missing"] == 0
        assert row["mean_ms"] is None
        assert row["p50_ms"] is None
        assert row["p95_ms"] is None
        assert row["min_ms"] is None
        assert row["max_ms"] is None

    markdown = bench.build_markdown(rows, [])
    assert "No latency data" in markdown
    assert "nothing was estimated or fabricated" in markdown


def test_load_cases_filters_non_dict_entries(tmp_path: Path, bench: Any) -> None:
    payload = {
        "total_cases": 1,
        "cases": [
            {"case": "a", "should_detect": True, "duration_ms": 7},
            "junk",
            None,
        ],
    }
    results_file = tmp_path / "eval.results.json"
    results_file.write_text(json.dumps(payload), encoding="utf-8")
    assert bench.load_cases(results_file) == [
        {"case": "a", "should_detect": True, "duration_ms": 7}
    ]


def test_load_cases_rejects_bad_payloads(tmp_path: Path, bench: Any) -> None:
    bad_file = tmp_path / "bad.results.json"
    bad_payloads = ["not-json", "[1, 2, 3]", json.dumps({"cases": "not-a-list"})]
    for payload in bad_payloads:
        bad_file.write_text(payload, encoding="utf-8")
        with pytest.raises(bench.LatencyError):
            bench.load_cases(bad_file)


def test_main_writes_markdown_summary(tmp_path: Path, bench: Any) -> None:
    results_file = tmp_path / "eval.results.json"
    results_file.write_text(
        json.dumps({
            "total_cases": 2,
            "cases": [
                {"case": "case-01", "should_detect": True, "duration_ms": 15},
                {"case": "case-02", "should_detect": False, "duration_ms": 45},
            ],
        }),
        encoding="utf-8",
    )
    out_file = tmp_path / "latency.md"
    exit_code = bench.main([str(results_file), "--output", str(out_file)])

    assert exit_code == 0
    markdown = out_file.read_text(encoding="utf-8")
    assert "| Case class | Cases |" in markdown
    assert "should-detect" in markdown
    assert "negative" in markdown
    assert "15.0" in markdown
    assert "45.0" in markdown
    assert "Honesty note" in markdown


def test_main_missing_file_reports_error(tmp_path: Path, bench: Any) -> None:
    missing = tmp_path / "does-not-exist.results.json"
    exit_code = bench.main([str(missing)])
    assert exit_code == 1
