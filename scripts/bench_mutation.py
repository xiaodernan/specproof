"""Mutation kill-rate benchmark CLI (interview metric: 变异杀死率 X%).

Usage:

  # Offline: bundled sample, no Docker / no network / no LLM.
  python scripts/bench_mutation.py --offline [--mutants N]

  # Real repo: existing mutation pipeline + contract/differential checks.
  python scripts/bench_mutation.py --target demo/spring-backend --mutants 10
  python scripts/bench_mutation.py --target golden-cases/case-01-auth-bypass
      --repo demo/spring-backend --test-class SpecProofGeneratedTest

Outputs (defaults):
  docs/eval/mutation-results.json   per-mutant records + kill-rate summary
  docs/eval/mutation-results.md     human summary with 变异杀死率 X%

Channels that cannot run (no docker/mvnw, missing spec/contract.py) are
reported as unavailable and the affected mutants are recorded as skipped —
never faked as killed.
"""

from __future__ import annotations

import argparse
import sys

from mutation_bench_lib import (
    DEFAULT_JSON,
    DEFAULT_MARKDOWN,
    OFFLINE_SAMPLE,
    BenchError,
    run_mutation_bench,
    run_mutation_pipeline,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bench_mutation",
        description="SpecProof 变异杀死率基准 (kill rate = killed / evaluated)",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="demo repo path or golden-case dir (pipeline mode; golden cases need --repo)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="demo repo used when --target is a golden case (default demo/spring-backend)",
    )
    parser.add_argument(
        "--test-class",
        default="",
        help="JUnit test class for the differential channel (empty = full test suite)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="run the bundled offline sample (scripts/mutation_sample), no Docker/network",
    )
    parser.add_argument(
        "--mutants",
        type=int,
        default=10,
        help="mutant cap (default 10; the offline sample has 6 hand-defined mutants)",
    )
    parser.add_argument("--json", type=str, default=str(DEFAULT_JSON), help="results JSON path")
    parser.add_argument(
        "--markdown", type=str, default=str(DEFAULT_MARKDOWN), help="markdown summary path"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.offline and args.target is not None:
        print("bench_mutation: --offline 与 --target 互斥", file=sys.stderr)
        return 2
    if not args.offline and args.target is None:
        print("bench_mutation: 需要 --offline 或 --target (--help 查看用法)", file=sys.stderr)
        return 2
    from pathlib import Path

    out_json = Path(args.json)
    out_md = Path(args.markdown)
    try:
        if args.offline:
            result = run_mutation_bench(
                OFFLINE_SAMPLE, args.mutants, out_json=out_json, out_md=out_md
            )
        else:
            result = run_mutation_pipeline(
                Path(args.target),
                repo=Path(args.repo) if args.repo else None,
                n=args.mutants,
                test_class=args.test_class,
                out_json=out_json,
                out_md=out_md,
            )
    except BenchError as exc:
        print(f"bench_mutation: 错误: {exc}", file=sys.stderr)
        return 2
    rate_pct = round(100.0 * result.kill_rate, 1)
    print(
        f"变异杀死率: {rate_pct:.1f}% "
        f"({result.killed}/{result.evaluated} killed, "
        f"{result.survived} survived, {result.skipped} skipped)"
    )
    print(f"结果 JSON: {out_json}")
    print(f"Markdown 报告: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
