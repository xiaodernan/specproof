"""A case skipped for an unreadable file must be COUNTED, not silently dropped.

The tolerance fix (an unreadable ``ground-truth.json`` costs that case, not the
whole run) survives the eval, but the skipped case used to vanish from the
accounting altogether: the summary still printed ``Not run: 0`` and the
sidecar's ``not_run`` stayed ``0``, so the denominator quietly shrank while the
run looked clean. That is the "假绿" shape this repo keeps fighting, so the skip
must land in the ``not_run`` column.

The transient Windows lock is simulated deterministically by patching
``Path.read_text`` -- the test does not depend on real file locking.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from cli.specproof.commands.eval import eval_cmd


def _make_case(root: Path, name: str, *, ground_truth: dict[str, Any]) -> Path:
    case = root / "cases" / name
    case.mkdir(parents=True)
    (case / "spec.md").write_text("# Case\n\nMust do it.\n", encoding="utf-8")
    (case / "ground-truth.json").write_text(json.dumps(ground_truth), encoding="utf-8")
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


def _run_with_one_locked_case(tmp_path: Path, monkeypatch: Any) -> Any:
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
    return _invoke(tmp_path, not_a_repo, monkeypatch)


def test_a_skipped_case_is_counted_in_not_run(tmp_path: Path, monkeypatch: Any) -> None:
    result = _run_with_one_locked_case(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    assert "SKIP case-b" in result.output, result.output
    # The summary must not claim nothing was skipped.
    assert re.search(r"Not run:\s+1\b", result.output), result.output
    # The machine-readable sidecar carries the same honest count.
    sidecar = json.loads((tmp_path / "report.results.json").read_text(encoding="utf-8"))
    assert sidecar["not_run"] == 1
    assert sidecar["total_cases"] == 1  # only case-a was measured


def test_a_malformed_ground_truth_is_counted_in_not_run(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    """Same accounting for a parse failure, not just a permission failure."""
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _make_case(
        tmp_path, "case-a",
        ground_truth={"should_detect": True, "expected_contract": "A-01"},
    )
    case_b = _make_case(
        tmp_path, "case-b",
        ground_truth={"should_detect": True, "expected_contract": "B-01"},
    )
    case_b.joinpath("ground-truth.json").write_text("{not json", encoding="utf-8")

    result = _invoke(tmp_path, not_a_repo, monkeypatch)

    assert result.exit_code == 0, result.output
    assert "SKIP case-b" in result.output, result.output
    assert re.search(r"Not run:\s+1\b", result.output), result.output
    sidecar = json.loads((tmp_path / "report.results.json").read_text(encoding="utf-8"))
    assert sidecar["not_run"] == 1
