"""#204 — a pipeline that never ran must not be scored as a recall miss.

`agent/graph.py` short-circuits on `state["errors"]` (`guard_errors`): a node
that refuses ends the run. When that happens the comparison never happened —
no worktrees, no differential, no findings — and the case has neither been
detected nor missed.

`eval_cmd` counted `should_detect` BEFORE the run and treated "no findings" as
`MISS`, so an aborted pipeline entered the denominator and stayed out of the
numerator: **Recall dropped while nothing had been compared**. That is the same
shape as #203 — "did not run" read as "ran and failed" — and it is worse here,
because the number it corrupts is the one CI gates on (`Recall: 100.0%`).

How this was found: a local untracked `.env` (real credentials, correctly
gitignored) tripped the repo-safety check, so `prepare` refused and every case
came back `MISS`. The eval reported `Recall: 0.0%` — reading as a detection
regression — when in fact nothing had been compared.

The case is now its own verdict, `NOT_RUN`, excluded from both sides of the
ratio and echoed per case. These tests drive the command with a stubbed graph
so the abort is deterministic and the gate does not depend on a stray file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd

ABORT = (
    "Repository safety check failed for base prepare (no_forbidden_files: "
    "forbidden file in repository (.env/key patterns): .env); worktree not created"
)


def _case_dir(root: Path, *, should_detect: bool = True) -> Path:
    case = root / "case-x"
    case.mkdir()
    (case / "spec.md").write_text(
        "# Case X\n\nMust do the thing.\n\n## Acceptance Criteria\n"
        "1. The thing must be done.\n",
        encoding="utf-8",
    )
    (case / "ground-truth.json").write_text(
        json.dumps(
            {
                "should_detect": should_detect,
                "expected_contract": "X-01",
                "expected_severity": "MAJOR",
                "expected_evidence_type": "base_pass_head_fail",
            }
        ),
        encoding="utf-8",
    )
    (case / "scenario.json").write_text(
        json.dumps({"version": "2.0", "base_ref": "base", "head_ref": "case-x-head"}),
        encoding="utf-8",
    )
    return case


def _run(root: Path, monkeypatch: Any, final: dict[str, Any]) -> str:
    class _Graph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return final

    monkeypatch.setattr("agent.graph.build_phase0_graph", lambda: _Graph())
    result = CliRunner().invoke(
        eval_cmd,
        [
            "--cases", str(root),
            "--repo", str(root),
            "--no-llm",
            "--output", str(root / "report.html"),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return result.output


def test_an_aborted_pipeline_is_reported_not_run(tmp_path: Path, monkeypatch: Any) -> None:
    _case_dir(tmp_path)
    output = _run(tmp_path, monkeypatch, {"errors": [ABORT], "confirmed_findings": []})

    assert "NOT_RUN" in output, output
    assert "worktree not created" in output, "the reason must reach the reader"
    assert "Should detect:      0" in output, (
        "the aborted case is still in the recall denominator:\n" + output
    )
    assert "Not run:            1" in output, output
    assert "Recall:             0.0%" not in output, (
        "an aborted run must not be reported as a 0% recall:\n" + output
    )


def test_a_completed_pipeline_is_still_counted(tmp_path: Path, monkeypatch: Any) -> None:
    """The control: without the abort, the case counts and misses as before."""
    _case_dir(tmp_path)
    output = _run(tmp_path, monkeypatch, {"confirmed_findings": []})

    assert "NOT_RUN" not in output, output
    assert "Not run:            0" in output, output
    assert "Should detect:      1" in output, output
    assert "MISS" in output, output


def test_the_counters_are_not_incremented_before_the_run() -> None:
    """Structural: the pre-run counting is what made an abort a miss.

    Read the source rather than the behaviour so a future refactor cannot move
    the increments back above `graph.invoke` while the behavioural tests stay
    green through some other path.
    """
    source = (
        Path(__file__).resolve().parents[2]
        / "cli" / "specproof" / "commands" / "eval.py"
    ).read_text(encoding="utf-8")
    invoke_at = source.index("final = graph.invoke(state)")
    for counter in ("total_should_detect += 1", "negative_cases += 1"):
        assert source.index(counter) > invoke_at, (
            f"`{counter}` moved back above the pipeline invocation — a case that "
            "never ran would re-enter the recall denominator"
        )
