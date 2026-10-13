"""#246 — an unreadable case file costs THAT case, not the whole run.

A real four-case eval died with a raw `PermissionError` traceback when one
`ground-truth.json` hit a transient Windows file lock; the fourth case never
ran and no numbers were produced. The eval measures a *pool*, so the case-file
reads must be tolerant: the affected case is skipped with its reason stated out
loud, and the remaining cases are still measured.

The transient lock is simulated deterministically by patching
`Path.read_text`, so the test does not depend on Windows file locking.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd


def _make_case(root: Path, name: str, *, ground_truth: dict[str, Any] | None) -> Path:
    case = root / "cases" / name
    case.mkdir(parents=True)
    (case / "spec.md").write_text("# Case\n\nMust do it.\n", encoding="utf-8")
    if ground_truth is not None:
        (case / "ground-truth.json").write_text(
            json.dumps(ground_truth), encoding="utf-8"
        )
    else:
        (case / "ground-truth.json").write_text("{not json", encoding="utf-8")
    (case / "scenario.json").write_text(
        json.dumps({"base_ref": "base", "head_ref": "head-v1"}), encoding="utf-8"
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
         "--output", str(root / "report.html")],
        catch_exceptions=False,
    )


def test_an_unreadable_ground_truth_skips_only_that_case(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    # --repo is a plain dir, so the ref preflight steps aside and the stubbed
    # graph runs; only case-b's ground truth is unreadable.
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _make_case(
        tmp_path, "case-a",
        ground_truth={"should_detect": True, "expected_contract": "A-01"},
    )
    _make_case(
        tmp_path, "case-b",
        ground_truth={"should_detect": True, "expected_contract": "B-01"},
    )
    real_read_text = Path.read_text

    def flaky_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "ground-truth.json" and "case-b" in str(self):
            raise PermissionError("[Errno 13] Permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    result = _invoke(tmp_path, not_a_repo, monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output, "a lock on one file must not kill the run"
    assert "SKIP case-b" in result.output, result.output
    assert "permission denied" in result.output, "the reason must reach the reader"
    # case-a was still measured — a MISS, but MEASURED, not lost with the run.
    assert "Should detect:      1" in result.output, result.output
    assert "MISS" in result.output, result.output


def test_a_malformed_ground_truth_skips_only_that_case(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    """Same tolerance for a parse failure: a broken file is a case-level skip."""
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _make_case(
        tmp_path, "case-a",
        ground_truth={"should_detect": True, "expected_contract": "A-01"},
    )
    _make_case(tmp_path, "case-b", ground_truth=None)

    result = _invoke(tmp_path, not_a_repo, monkeypatch)

    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output
    assert "SKIP case-b" in result.output, result.output
    assert "Should detect:      1" in result.output, result.output
