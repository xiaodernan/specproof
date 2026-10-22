"""The full-pool runner must be resumable, stable and honest about exit codes.

`scripts/run_full_eval.py` is the command the nightly CI job would run
and the command an operator runs on a laptop that will be interrupted.
Three things have to hold, and each is pinned here:

- the evaluation it runs always passes ``--resume`` ⇒ ⇒ ⇒ a first run is
  unaffected (there is no sidecar yet) and every later run continues;
- the report AND the sidecar the evaluation derives from it live in the
  SAME directory ⇒ ⇒ ⇒ that directory is the thing a cache has to keep
  ⇒ ⇒ ⇒ "resume" has something to resume from;
- the exit code is the evaluation's own ⇒ ⇒ ⇒ a caller can gate on it
  without parsing anything.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_full_eval import (
    build_command,
    read_sidecar,
    summarise,
)

REPO = Path(__file__).resolve().parents[2]


def test_the_command_always_resumes() -> None:
    command = build_command(
        cases=REPO / "golden-cases",
        repo=REPO,
        output_dir=REPO / "reports" / "full-eval",
    )
    assert "--resume" in command
    assert "--no-llm" in command
    assert "eval" in command


def test_the_report_and_the_sidecar_live_in_the_same_directory() -> None:
    """The sidecar's name is derived from the report's name, so putting
    the report inside the output directory puts the sidecar there too
    ⇒ ⇒ ⇒ that is the directory a cache keeps."""
    output_dir = REPO / "reports" / "full-eval"
    command = build_command(
        cases=REPO / "golden-cases", repo=REPO, output_dir=output_dir,
    )
    report = Path(command[command.index("--output") + 1])
    assert report.parent == output_dir
    assert report.name == "eval-report.html"
    sidecar = report.with_suffix(".results.jsonl")
    assert sidecar.parent == output_dir


def test_the_llm_flag_is_off_unless_asked() -> None:
    plain = build_command(cases=REPO, repo=REPO, output_dir=REPO / "r")
    assert "--no-llm" in plain
    assert "--llm" not in plain
    with_llm = build_command(cases=REPO, repo=REPO, output_dir=REPO / "r", llm=True)
    assert "--llm" in with_llm
    assert "--no-llm" not in with_llm


def test_a_missing_sidecar_reads_as_nothing(tmp_path) -> None:
    assert read_sidecar(tmp_path) == {}
    assert "no sidecar" in summarise({})


def test_the_summary_says_the_pool_the_metrics_and_the_verdict(tmp_path) -> None:
    sidecar = {
        "total_cases": 87,
        "not_run": 2,
        "recall": 100.0,
        "precision": 95.5,
        "f1": 97.7,
        "false_positives": 1,
        "resumed_cases": 12,
        "acceptance": {"status": "PASS"},
        "pool_snapshot": {"total_kept": 87, "positive_cases": 52,
                          "negative_cases": 35},
    }
    path = tmp_path / "eval-report.results.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    loaded = read_sidecar(tmp_path)
    text = summarise(loaded)
    assert "cases=87" in text
    assert "recall=100.0" in text
    assert "acceptance=PASS" in text
    assert "reused_from_an_earlier_run=12" in text
    assert "pool=87 (pos 52 / neg 35)" in text


def test_the_script_prints_its_own_command_and_exits_zero() -> None:
    """--dry-run is how a caller (or a gate) reads the command without
    spending a full-pool run."""
    import os

    completed = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "run_full_eval.py"), "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO),
        # The child's stdout is the console's encoding unless it is told
        # otherwise, and the repository path is not ASCII.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, completed.stderr
    assert "--resume" in completed.stdout
    assert "eval" in completed.stdout
