"""Run the FULL golden-case evaluation, resumably, with one command.

The full pool is ~87 measured cases and the pipeline does real Maven
builds per case ⇒ ⇒ ⇒ a run takes hours (measured: ~23 min/case on a
contended laptop) ⇒ ⇒ ⇒ two consequences:

1. a run that is killed must not throw the measured hours away ⇒ ⇒ ⇒
   the evaluation writes one JSON line per case as it goes (#377) and
   this script always passes ``--resume`` ⇒ ⇒ ⇒ a re-run picks up the
   cases whose inputs did not change and re-measures only the rest
   (#378, proven on the real pipeline: 623 s → 14.2 s, see ledger
   ## #385);
2. the run's records must live in a STABLE place, or "resume" has
   nothing to resume from ⇒ ⇒ ⇒ the output directory defaults to
   ``reports/full-eval/`` (gitignored) ⇒ ⇒ ⇒ and a CI job can put that
   directory in a cache ⇒ ⇒ ⇒ a re-run of a timed-out job continues.

The exit code is the acceptance verdict's: zero only when the run
PASSED ⇒ ⇒ ⇒ a caller can gate on it without parsing anything.

    python scripts/run_full_eval.py
    python scripts/run_full_eval.py --cases golden-cases --repo .
    python scripts/run_full_eval.py --dry-run      # print the command only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "full-eval"
DEFAULT_CASES = REPO_ROOT / "golden-cases"


def build_command(
    *,
    cases: Path,
    repo: Path,
    output_dir: Path,
    python: str = sys.executable,
    llm: bool = False,
    attempts: int = 1,
) -> list[str]:
    """The command this script runs.

    ``--resume`` is ALWAYS on: on a first run it is a no-op (there is no
    sidecar to read), and on every later run it is the whole point. The
    report path is inside the output directory, so the sidecar the
    evaluation derives from it (``<report>.results.jsonl``) lands there
    too ⇒ ⇒ ⇒ and that is the path a cache has to keep.

    ``--attempts`` says how many times a case may be measured. A case
    whose DETECTION is unstable would otherwise decide the pool's recall
    by luck (ledger #391) ⇒ ⇒ ⇒ the nightly job should ask for more
    than one attempt and read BOTH numbers: the recall (can this defect
    be found) and the first-try recall (was it found the first time).
    """
    return [
        python, "-m", "cli.specproof.main", "eval",
        "--cases", str(cases),
        "--repo", str(repo),
        "--output", str(output_dir / "eval-report.html"),
        "--resume",
        "--attempts", str(max(1, int(attempts))),
        *(["--llm"] if llm else ["--no-llm"]),
    ]


def read_sidecar(output_dir: Path) -> dict[str, Any]:
    """The evaluation's own record, or an empty mapping when there is none."""
    path = output_dir / "eval-report.results.json"
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def summarise(sidecar: dict[str, Any]) -> str:
    """One line a human can read: the pool, the metrics, the verdict."""
    if not sidecar:
        return "no sidecar yet (the run has not finished)"
    metrics = sidecar.get("acceptance") or {}
    status = metrics.get("status", "?")
    pool = sidecar.get("pool_snapshot") or {}
    parts = [
        f"cases={sidecar.get('total_cases', '?')}",
        f"not_run={sidecar.get('not_run', '?')}",
        f"pool={pool.get('total_kept', '?')}"
        f" (pos {pool.get('positive_cases', '?')} / neg {pool.get('negative_cases', '?')})",
        f"recall={sidecar.get('recall')}",
        f"precision={sidecar.get('precision')}",
        f"f1={sidecar.get('f1')}",
        f"false_positives={sidecar.get('false_positives', '?')}",
        f"acceptance={status}",
    ]
    if sidecar.get("resumed_cases"):
        parts.append(f"reused_from_an_earlier_run={sidecar['resumed_cases']}")
    return "  ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(DEFAULT_CASES),
                        help="the golden cases directory")
    parser.add_argument("--repo", default=str(REPO_ROOT),
                        help="the repository under test")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="where the report and the resumable sidecar live")
    parser.add_argument("--llm", action="store_true",
                        help="allow the LLM-assisted nodes (default: deterministic)")
    parser.add_argument("--attempts", type=int, default=1,
                        help="how many times a case may be measured; a case "
                             "whose detection is unstable would otherwise "
                             "decide the pool's recall by luck (ledger #391)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the command and exit")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    command = build_command(
        cases=Path(args.cases),
        repo=Path(args.repo),
        output_dir=output_dir,
        llm=args.llm,
        attempts=args.attempts,
    )
    if args.dry_run:
        print(" ".join(command))
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[full-eval] running: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=str(REPO_ROOT))
    sidecar = read_sidecar(output_dir)
    print(f"[full-eval] {summarise(sidecar)}", flush=True)
    print(
        "[full-eval] the per-case records (the resumable sidecar) are in "
        f"{output_dir / 'eval-report.results.jsonl'}",
        flush=True,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
