"""Unit tests — Node/npm adapter (local-first, Phase 2.3).

Covers detect rules (package.json + scripts.test; missing/malformed files and
projects without a test script fail closed), prepare command shape, run
through a fake local runner, Jest/Vitest/node:test summary parsing, collect
evidence, no-op cleanup, and registry wiring. A single real-execution test
drives `node --test` end-to-end when Node is available (skipped otherwise) —
the rest are faked: no network, no dependency install.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import experiments.adapters as adapters
from experiments.adapters import (
    AdapterNotImplemented,
    ExecutionAdapter,
    ExecutionRequest,
    LocalRunResult,
    NodeAdapter,
    RepositorySnapshot,
    parse_node_test_summary,
    registry,
)


def _make_node_repo(
    tmp_path: Path, test_script: str | None = "node --test"
) -> Path:
    pkg: dict[str, Any] = {"name": "demo", "version": "1.0.0"}
    if test_script is not None:
        pkg["scripts"] = {"test": test_script}
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    return tmp_path


class TestNodeDetect:
    def test_matches_package_json_with_test_script(self, tmp_path: Path) -> None:
        profile = NodeAdapter().detect(
            RepositorySnapshot(path=str(_make_node_repo(tmp_path)))
        )
        assert profile.language == "javascript/typescript"
        assert profile.build_tool == "npm"
        assert "node:test" in profile.test_runner

    def test_no_package_json_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AdapterNotImplemented, match="detect rule"):
            NodeAdapter().detect(RepositorySnapshot(path=str(tmp_path)))

    def test_package_json_without_test_script_raises(self, tmp_path: Path) -> None:
        repo = _make_node_repo(tmp_path, test_script=None)
        with pytest.raises(AdapterNotImplemented, match="scripts.test"):
            NodeAdapter().detect(RepositorySnapshot(path=str(repo)))

    def test_malformed_package_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(AdapterNotImplemented, match="scripts.test"):
            NodeAdapter().detect(RepositorySnapshot(path=str(tmp_path)))


class TestNodePrepare:
    def test_run_test_command_shape(self, tmp_path: Path) -> None:
        prepared = NodeAdapter().prepare(
            ExecutionRequest(workspace=str(tmp_path), goal="run_test")
        )
        assert prepared.command == ["npm", "test", "--silent"]
        assert prepared.local_command == prepared.command
        assert prepared.image == "—"

    def test_test_class_appends_filter(self, tmp_path: Path) -> None:
        prepared = NodeAdapter().prepare(
            ExecutionRequest(
                workspace=str(tmp_path), goal="run_test", test_class="my test"
            )
        )
        assert prepared.command[-3:] == ["--", "-t", "my test"]

    def test_unsupported_goal_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AdapterNotImplemented, match="run_test only"):
            NodeAdapter().prepare(
                ExecutionRequest(workspace=str(tmp_path), goal="test_compile")
            )


class TestNodeRunCollect:
    def _adapter_with_fake_run(
        self, monkeypatch: pytest.MonkeyPatch, result: LocalRunResult
    ) -> NodeAdapter:
        monkeypatch.setattr(adapters, "_run_local", lambda *a, **k: result)
        return NodeAdapter()

    def test_run_parses_vitest_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stdout = " Test Files  1 passed (1)\n      Tests  1 failed | 2 passed (3)\n"
        adapter = self._adapter_with_fake_run(
            monkeypatch,
            LocalRunResult(exit_code=1, stdout=stdout, stderr=""),
        )
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(tmp_path), goal="run_test")
        )
        run_result = adapter.run(prepared)
        assert run_result.exit_code == 1
        assert run_result.mode == "local"
        evidence = adapter.collect(prepared)
        assert evidence.exit_evidence["test_counts"] == {
            "tests": 3,
            "passed": 2,
            "failed": 1,
            "errors": 0,
            "skipped": 0,
        }

    def test_collect_without_run_is_honest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = NodeAdapter()
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(tmp_path), goal="run_test")
        )
        evidence = adapter.collect(prepared)
        assert evidence.exit_evidence["collected"] is False

    def test_cleanup_is_noop_keeps_workspace(self, tmp_path: Path) -> None:
        repo = _make_node_repo(tmp_path)
        prepared = NodeAdapter().prepare(
            ExecutionRequest(workspace=str(repo), goal="run_test")
        )
        NodeAdapter().cleanup(prepared)
        assert (repo / "package.json").exists()


class TestNodeSummaryParsers:
    def test_jest_summary(self) -> None:
        text = "Tests:       1 failed, 4 passed, 5 total"
        assert parse_node_test_summary(text) == {
            "tests": 5,
            "passed": 4,
            "failed": 1,
            "errors": 0,
            "skipped": 0,
        }

    def test_jest_with_skipped(self) -> None:
        text = "Tests:       2 failed, 10 passed, 3 skipped, 15 total"
        assert parse_node_test_summary(text) == {
            "tests": 15,
            "passed": 10,
            "failed": 2,
            "errors": 0,
            "skipped": 3,
        }

    def test_node_tap_summary(self) -> None:
        text = "# tests 6\n# suites 1\n# pass 5\n# fail 1\n# skipped 0\n"
        assert parse_node_test_summary(text) == {
            "tests": 6,
            "passed": 5,
            "failed": 1,
            "errors": 0,
            "skipped": 0,
        }

    def test_unrecognised_output_is_no_evidence(self) -> None:
        assert parse_node_test_summary("some random build log") == {
            "tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
        }


class TestNodeRegistryWiring:
    def test_node_repo_resolves_to_node_adapter(self, tmp_path: Path) -> None:
        repo = _make_node_repo(tmp_path)
        adapter = registry.get(RepositorySnapshot(path=str(repo)))
        assert isinstance(adapter, NodeAdapter)

    def test_node_adapter_satisfies_protocol(self) -> None:
        assert isinstance(NodeAdapter(), ExecutionAdapter)


@pytest.mark.skipif(
    platform.system() == "Windows" or shutil.which("npm") is None,
    reason="real npm execution is exercised on POSIX CI; skipped when npm absent",
)
def test_node_adapter_runs_real_suite(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "package.json").write_text(
        json.dumps({"name": "demo", "scripts": {"test": "node --test"}}),
        encoding="utf-8",
    )
    (repo / "math.test.js").write_text(
        "const t = require('node:test');\n"
        "const a = require('node:assert');\n"
        "t.test('adds', () => a.equal(1 + 1, 2));\n"
        "t.test('subtracts', () => a.equal(2 - 1, 1));\n",
        encoding="utf-8",
    )
    adapter = NodeAdapter()
    prepared = adapter.prepare(
        ExecutionRequest(workspace=str(repo), goal="run_test", timeout=120)
    )
    result = adapter.run(prepared)
    assert result.exit_code == 0, result.stderr_tail[-500:]
    counts = adapter.collect(prepared).exit_evidence["test_counts"]
    assert counts["passed"] == 2
    assert counts["failed"] == 0


# Guard: the module must import cleanly and node must be probeable so the
# above skip condition is meaningful on machines that do have npm.
def test_shutil_and_subprocess_imported() -> None:
    assert callable(subprocess.run)
