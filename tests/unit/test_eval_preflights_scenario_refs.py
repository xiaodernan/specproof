"""#243 — `specproof eval` must resolve scenario refs BEFORE it runs.

A scenario's `base_ref`/`head_ref` name git refs the pipeline checks out to
build its worktrees. When `--repo` cannot resolve one of them, the pipeline
cannot run that case at all — but the failure surfaced mid-run as a `NOT_RUN`
(or, before #204, as a `MISS`), forcing the operator to reverse-engineer a
setup problem out of a pipeline message.

The command now resolves every scenario ref against `--repo` up front and
aborts with the exact case + ref named. Two boundaries are pinned here:

- a missing ref fails loud, naming the case and the ref;
- when `--repo` is NOT a git repository the preflight steps aside, because the
  pipeline reports the real problem and a "ref missing" message would be noise
  on top of it (the other eval tests drive the command with a non-git tmp dir).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd


def _git_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-qm", "init"],
        cwd=repo, check=True,
    )
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "tag", "base"], cwd=repo, check=True)
    return repo


def _case_dir(root: Path, head_ref: str) -> Path:
    case = root / "cases" / "case-x"
    case.mkdir(parents=True)
    (case / "spec.md").write_text(
        "# Case X\n\nMust do the thing.\n\n## Acceptance Criteria\n"
        "1. The thing must be done.\n",
        encoding="utf-8",
    )
    (case / "ground-truth.json").write_text(
        json.dumps({"should_detect": True, "expected_contract": "X-01"}),
        encoding="utf-8",
    )
    (case / "scenario.json").write_text(
        json.dumps({"version": "2.0", "base_ref": "base", "head_ref": head_ref}),
        encoding="utf-8",
    )
    return case


def _invoke(root: Path, repo: Path, monkeypatch: Any) -> Any:
    class _Graph:
        def invoke(self, _state: dict[str, Any]) -> dict[str, Any]:
            return {"confirmed_findings": []}

    monkeypatch.setattr("agent.graph.build_phase0_graph", lambda: _Graph())
    return CliRunner().invoke(
        eval_cmd,
        ["--cases", str(root / "cases"), "--repo", str(repo),
         "--no-llm", "--output", str(root / "report.html")],
        catch_exceptions=False,
    )


def test_a_missing_ref_aborts_before_the_run_naming_the_case_and_ref(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = _git_repo(tmp_path)
    _case_dir(tmp_path, head_ref="case-x-head")  # tag deliberately NOT created

    result = _invoke(tmp_path, repo, monkeypatch)

    assert result.exit_code != 0, result.output
    assert "case-x-head" in result.output, (
        "the failing ref must be named, not left to a mid-pipeline message:\n"
        + result.output
    )
    assert "case-x" in result.output, result.output


def test_resolvable_refs_pass_the_preflight_and_the_run_proceeds(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = _git_repo(tmp_path)
    _case_dir(tmp_path, head_ref="case-x-head")
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "tag", "case-x-head"], cwd=repo, check=True)

    result = _invoke(tmp_path, repo, monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Running evaluation across 1 golden cases" in result.output


def test_a_non_git_repo_steps_aside_so_the_pipeline_reports_the_real_problem(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The other eval tests drive the command with a plain tmp dir; a preflight
    that fired there would abort runs the pipeline itself handles."""
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _case_dir(tmp_path, head_ref="case-x-head")

    result = _invoke(tmp_path, not_a_repo, monkeypatch)

    assert result.exit_code == 0, result.output
