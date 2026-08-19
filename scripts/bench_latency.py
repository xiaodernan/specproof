"""Compute verification-latency stats from `specproof eval` results JSONs.

Reads the machine-readable sidecars written by `specproof eval`
(`*.results.json`) and reports, per case class (should_detect true/false)
plus an overall row, the mean / p50 / p95 / min / max of the optional
per-case `duration_ms` field.

Honesty contract: `duration_ms` is case-level whole-pipeline wall clock
captured by eval around `graph.invoke`; the Phase 0 graph does not expose
per-stage timestamps, so no stage-level numbers are invented here. Cases
whose `duration_ms` is missing or not a non-negative number are counted as
"missing" and excluded from the statistics.

Usage:
    python scripts/bench_latency.py docs/eval/eval-c1.results.json
    python scripts/bench_latency.py --output latency.md *.results.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DURATION_FIELD = "duration_ms"
CLASS_FIELD = "should_detect"


class LatencyError(Exception):
    """A results file could not be read or parsed."""


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Return the `cases` list from one eval results JSON."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LatencyError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LatencyError(f"{path}: top-level JSON value is not an object")
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise LatencyError(f"{path}: 'cases' is not a list")
    return [case for case in cases if isinstance(case, dict)]


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Return the pct-th percentile (0..100) with linear interpolation.

    Ranks are pct/100 * (n - 1) over the sorted values; non-integer ranks
    interpolate between neighbours (the numpy "linear" default). Returns
    None for an empty sequence.
    """
    if not values:
        return None
    if pct < 0.0 or pct > 100.0:
        raise ValueError(f"percentile must be in [0, 100], got {pct}")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100.0 * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def p50(values: Sequence[float]) -> float | None:
    """Median of *values* (50th percentile)."""
    return percentile(values, 50.0)


def p95(values: Sequence[float]) -> float | None:
    """95th percentile of *values* (SLO p95)."""
    return percentile(values, 95.0)


def mean(values: Sequence[float]) -> float | None:
    """Arithmetic mean of *values* (None when empty)."""
    if not values:
        return None
    return sum(values) / len(values)


def _valid_duration(case: dict[str, Any]) -> float | None:
    """The case's duration_ms as a float, or None when unusable.

    Booleans, non-numeric values, negative numbers and non-finite floats
    (NaN, infinities) are not timings; they are treated as missing rather
    than coerced.
    """
    raw = case.get(DURATION_FIELD)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value < 0.0:
        return None
    return value


def collect_durations(
    cases: Sequence[dict[str, Any]], should_detect: bool | None,
) -> tuple[list[float], int]:
    """Split a case class into (valid durations, missing-duration count).

    should_detect=None collects every case; True/False filters by the
    `should_detect` field (a case without the field buckets as False).
    """
    durations: list[float] = []
    missing = 0
    for case in cases:
        in_class = should_detect is None or bool(case.get(CLASS_FIELD)) == should_detect
        if not in_class:
            continue
        value = _valid_duration(case)
        if value is None:
            missing += 1
        else:
            durations.append(value)
    return durations, missing


def class_stats(
    cases: Sequence[dict[str, Any]], label: str, should_detect: bool | None,
) -> dict[str, Any]:
    """Latency statistics for one case class."""
    durations, missing = collect_durations(cases, should_detect)
    if should_detect is None:
        case_count = len(cases)
    else:
        case_count = sum(
            1 for case in cases if bool(case.get(CLASS_FIELD)) == should_detect
        )
    return {
        "class": label,
        "cases": case_count,
        "timed": len(durations),
        "missing": missing,
        "mean_ms": mean(durations),
        "p50_ms": p50(durations),
        "p95_ms": p95(durations),
        "min_ms": min(durations) if durations else None,
        "max_ms": max(durations) if durations else None,
    }


def aggregate_stats(cases: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-class and overall latency rows."""
    return [
        class_stats(cases, "should-detect", True),
        class_stats(cases, "negative", False),
        class_stats(cases, "all", None),
    ]


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}"


def build_markdown(
    stats: Sequence[dict[str, Any]],
    files: Sequence[str],
    errors: Sequence[str] = (),
) -> str:
    """Render the latency summary as markdown."""
    lines = [
        "# Verification Latency (case-level pipeline wall clock)",
        "",
        f"- Input files: {len(files)}",
        f"- Timing field: `{DURATION_FIELD}` per case, measured by "
        "`specproof eval` around the whole pipeline invocation.",
        "- Honesty note: the Phase 0 pipeline exposes no per-stage "
        "timestamps, so these statistics are case-level only — no stage "
        "numbers are estimated.",
    ]
    if errors:
        lines.append("- Read errors (these files contributed no cases):")
        for error in errors:
            lines.append(f"  - {error}")
    lines += [
        "",
        "| Case class | Cases | Timed | Missing | Mean ms | p50 ms | p95 ms | Min ms | Max ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stats:
        lines.append(
            f"| {row['class']} | {row['cases']} | {row['timed']} | "
            f"{row['missing']} | {_fmt_ms(row['mean_ms'])} | "
            f"{_fmt_ms(row['p50_ms'])} | {_fmt_ms(row['p95_ms'])} | "
            f"{_fmt_ms(row['min_ms'])} | {_fmt_ms(row['max_ms'])} |"
        )
    if not any(row["timed"] for row in stats):
        lines += [
            "",
            "**No latency data**: the input contains no cases with a numeric "
            f"`{DURATION_FIELD}`; nothing was estimated or fabricated.",
        ]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench_latency",
        description="Compute p50/p95/mean verification latency per case class "
        "from `specproof eval` results JSONs.",
    )
    parser.add_argument(
        "results", nargs="+", metavar="RESULTS_JSON",
        help="Eval results JSON sidecars written by `specproof eval`.",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Write the markdown summary to this path (default: stdout).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    for raw in args.results:
        path = Path(raw)
        if not path.exists():
            errors.append(f"{path}: file not found")
            continue
        try:
            cases.extend(load_cases(path))
        except LatencyError as exc:
            errors.append(str(exc))
    markdown = build_markdown(aggregate_stats(cases), args.results, errors)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print(f"Latency summary written to {out}")
    else:
        sys.stdout.write(markdown)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
