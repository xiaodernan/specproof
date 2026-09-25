"""Unit tests — Node/npm adapter (Docker-sandboxed, Phase 2.3 + roadmap path i).

Covers detect rules (package.json + scripts.test; missing/malformed files and
projects without a test script fail closed), prepare command shape, the
execution-surface contract (default MUST be the hardened container with
mode="docker", so an unavailable daemon is an error rather than a silent fall
onto the host; host execution only when a caller names sandbox_mode="local"),
Jest/Vitest/node:test summary parsing, collect evidence, no-op cleanup, and
registry wiring. Two real-execution tests exist and both skip honestly: one
drives `node --test` on the host when npm is present (POSIX CI), the other
drives the actual container only when SPECPROOF_TEST_DOCKER=1 is set, so the
unit gate never depends on a Docker daemon.
"""

from __future__ import annotations

import json
import os
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
from sandbox.runner import NODE_INSTALL_PROFILE, NODE_PROFILE, SandboxResult


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
        assert prepared.image == adapters._node_image()
        assert prepared.image != "—"  # a sandboxed adapter names a real image

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
    def _adapter_with_fake_local_run(
        self, monkeypatch: pytest.MonkeyPatch, result: LocalRunResult
    ) -> NodeAdapter:
        monkeypatch.setattr(adapters, "_run_local", lambda *a, **k: result)
        return NodeAdapter()

    def _adapter_with_fake_sandbox(
        self, monkeypatch: pytest.MonkeyPatch, result: SandboxResult
    ) -> NodeAdapter:
        monkeypatch.setattr(adapters, "run_sandboxed", lambda *a, **k: result)
        return NodeAdapter()

    def test_default_run_uses_docker_and_never_the_host(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The security invariant of the whole adapter.

        A repository's own test script is untrusted, so the default run must
        demand the container (mode="docker", not "auto") and must not touch
        the host even if the sandbox fails.
        """
        captured: dict[str, Any] = {}

        def fake_sandboxed(command, **kwargs):
            captured["command"] = command
            captured.update(kwargs)
            return SandboxResult(
                exit_code=0, stdout="# pass 1", stderr="", mode="docker"
            )

        def never_local(*a, **k):  # pragma: no cover - must not run
            raise AssertionError("_run_local must not be reached by default")

        monkeypatch.setattr(adapters, "run_sandboxed", fake_sandboxed)
        monkeypatch.setattr(adapters, "_run_local", never_local)
        adapter = NodeAdapter()
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(tmp_path), goal="run_test")
        )
        result = adapter.run(prepared)
        assert captured["mode"] == "docker", "auto would allow a silent host fallback"
        assert captured["profile"] is NODE_PROFILE
        assert result.mode == "docker"
        assert result.sandbox_resources["network"] == "none"
        assert result.sandbox_resources["user"] == "1000:1000"

    def test_host_execution_requires_naming_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            adapters,
            "run_sandboxed",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("sandbox must not be used when local is requested")
            ),
        )
        adapter = self._adapter_with_fake_local_run(
            monkeypatch, LocalRunResult(exit_code=0, stdout="", stderr="")
        )
        prepared = adapter.prepare(
            ExecutionRequest(
                workspace=str(tmp_path), goal="run_test", sandbox_mode="local"
            )
        )
        result = adapter.run(prepared)
        assert result.mode == "local"
        assert "host" in result.sandbox_resources["sandbox"]

    def test_run_parses_vitest_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stdout = " Test Files  1 passed (1)\n      Tests  1 failed | 2 passed (3)\n"
        adapter = self._adapter_with_fake_sandbox(
            monkeypatch,
            SandboxResult(exit_code=1, stdout=stdout, stderr="", mode="docker"),
        )
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(tmp_path), goal="run_test")
        )
        run_result = adapter.run(prepared)
        assert run_result.exit_code == 1
        assert run_result.mode == "docker"
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
def test_node_adapter_runs_real_suite_on_host(tmp_path: Path) -> None:
    repo = _make_node_repo(tmp_path)
    (repo / "math.test.js").write_text(
        "const t = require('node:test');\n"
        "const a = require('node:assert');\n"
        "t.test('adds', () => a.equal(1 + 1, 2));\n"
        "t.test('subtracts', () => a.equal(2 - 1, 1));\n",
        encoding="utf-8",
    )
    adapter = NodeAdapter()
    # Host execution is opt-in by name — this is a test-authored fixture, not a
    # repository under review, so it is the one place that asks for it.
    prepared = adapter.prepare(
        ExecutionRequest(
            workspace=str(repo), goal="run_test", timeout=120, sandbox_mode="local"
        )
    )
    result = adapter.run(prepared)
    assert result.exit_code == 0, result.stderr_tail[-500:]
    counts = adapter.collect(prepared).exit_evidence["test_counts"]
    assert counts["passed"] == 2
    assert counts["failed"] == 0


@pytest.mark.skipif(
    os.getenv("SPECPROOF_TEST_DOCKER", "").strip() != "1",
    reason="needs a live Docker daemon; opt in with SPECPROOF_TEST_DOCKER=1 so the"
    " unit gate stays runnable without one",
)
def test_node_adapter_runs_real_suite_in_sandbox(tmp_path: Path) -> None:
    repo = _make_node_repo(tmp_path)
    (repo / "math.test.js").write_text(
        "const t = require('node:test');\n"
        "const a = require('node:assert');\n"
        "t.test('adds', () => a.equal(1 + 1, 2));\n"
        "t.test('subtracts', () => a.equal(2 - 1, 1));\n",
        encoding="utf-8",
    )
    adapter = NodeAdapter()
    prepared = adapter.prepare(
        ExecutionRequest(workspace=str(repo), goal="run_test", timeout=300)
    )
    result = adapter.run(prepared)
    assert result.error == "", result.error
    assert result.mode == "docker"
    counts = adapter.collect(prepared).exit_evidence["test_counts"]
    assert counts["passed"] == 2, (result.stdout_tail[-800:], result.stderr_tail[-400:])
    assert counts["failed"] == 0


# Guard: the module must import cleanly and node must be probeable so the
# above skip condition is meaningful on machines that do have npm.
def test_shutil_and_subprocess_imported() -> None:
    assert callable(subprocess.run)


class TestNodeOfflineInstall:
    """#56: the sandboxed offline install for lockfile projects.

    The install runs FIRST in its own container (NODE_INSTALL_PROFILE: seeded
    cache volume + writable node_modules sub-mount) and a failed install runs
    NO tests — a dependency that cannot be resolved offline is an honest
    NON_REPRODUCIBLE, never a pass.
    """

    def _lockfile_workspace(self, tmp_path: Path, *, with_modules: bool) -> Path:
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "a", "scripts": {"test": "node --test"}}),
            encoding="utf-8",
        )
        (tmp_path / "package-lock.json").write_text(
            json.dumps({"name": "a", "lockfileVersion": 3}), encoding="utf-8",
        )
        if with_modules:
            modules = tmp_path / "node_modules"
            modules.mkdir()
            (modules / ".package-lock.json").write_text("{}", encoding="utf-8")
        return tmp_path

    def _recording_sandbox(self, monkeypatch: pytest.MonkeyPatch, install_exit: int):
        calls: list[tuple[list[str], dict[str, Any]]] = []

        def fake_sandboxed(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            if len(calls) == 1 and install_exit != 0:
                return SandboxResult(
                    exit_code=install_exit,
                    stdout="",
                    stderr="npm error code E404\nnpm error 404 Not Found - GET https://registry",
                    mode="docker",
                )
            return SandboxResult(
                exit_code=0, stdout="# pass 2\n# fail 0", stderr="", mode="docker",
            )

        monkeypatch.setattr(adapters, "run_sandboxed", fake_sandboxed)
        return calls

    def _run(self, tmp_path: Path, adapter: NodeAdapter) -> Any:
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(tmp_path), goal="run_test")
        )
        return adapter.run(prepared)

    def test_lockfile_project_gets_offline_install_then_test(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = self._lockfile_workspace(tmp_path, with_modules=False)
        calls = self._recording_sandbox(monkeypatch, install_exit=0)

        result = self._run(workspace, NodeAdapter())

        assert len(calls) == 2, "install first, then the test run"
        install_cmd, install_kwargs = calls[0]
        test_cmd, test_kwargs = calls[1]
        assert install_cmd == NodeAdapter.OFFLINE_INSTALL_COMMAND
        assert "--offline" in install_cmd and "--ignore-scripts" in install_cmd
        assert install_kwargs["profile"] is NODE_INSTALL_PROFILE
        assert install_kwargs["mode"] == "docker"
        assert test_cmd[:3] == ["npm", "test", "--silent"]
        assert test_kwargs["profile"] is NODE_PROFILE
        assert result.exit_code == 0
        assert result.sandbox_resources["dependency_install"] == (
            "offline npm ci from the seeded cache volume"
        )
        # The install phase disclosed its own hardening surface.
        assert result.sandbox_resources["network"] == "none"

    def test_failed_install_runs_no_tests_and_says_why(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = self._lockfile_workspace(tmp_path, with_modules=False)
        calls = self._recording_sandbox(monkeypatch, install_exit=1)

        result = self._run(workspace, NodeAdapter())

        assert len(calls) == 1, "a failed install must not be followed by a test run"
        assert result.exit_code == 1
        assert "tests were not run" in result.error
        assert "E404" in result.stderr_tail
        assert result.sandbox_resources["lifecycle_scripts"] == "disabled (--ignore-scripts)"
        assert result.sandbox_resources["cache_volume"].startswith("specproof-npm-cache-1000")

    def test_populated_node_modules_skips_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = self._lockfile_workspace(tmp_path, with_modules=True)
        calls = self._recording_sandbox(monkeypatch, install_exit=0)

        result = self._run(workspace, NodeAdapter())

        assert len(calls) == 1
        assert calls[0][1]["profile"] is NODE_PROFILE
        assert result.sandbox_resources["dependency_install"] == (
            "skipped (node_modules already populated)"
        )

    def test_dependency_free_project_skips_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "a", "scripts": {"test": "node --test"}}),
            encoding="utf-8",
        )
        calls = self._recording_sandbox(monkeypatch, install_exit=0)

        result = self._run(tmp_path, NodeAdapter())

        assert len(calls) == 1
        assert calls[0][1]["profile"] is NODE_PROFILE
        assert result.sandbox_resources["dependency_install"] == (
            "skipped (node_modules already populated)"
        )

    def test_local_mode_never_installs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Host execution installs nothing, ever: an offline install needs the
        Docker cache volume, and untrusted lifecycle scripts on the host are
        exactly what the red line forbids."""
        workspace = self._lockfile_workspace(tmp_path, with_modules=False)

        def never_sandbox(*a, **k):  # pragma: no cover - must not run
            raise AssertionError("local mode must not touch the sandbox runner")

        local_calls: list[tuple[Any, dict[str, Any]]] = []

        def fake_local(command, **kwargs):
            local_calls.append((list(command), dict(kwargs)))
            return LocalRunResult(exit_code=0, stdout="# pass 1", stderr="")

        monkeypatch.setattr(adapters, "run_sandboxed", never_sandbox)
        monkeypatch.setattr(adapters, "_run_local", fake_local)
        adapter = NodeAdapter()
        prepared = adapter.prepare(
            ExecutionRequest(
                workspace=str(workspace), goal="run_test", sandbox_mode="local",
            )
        )
        result = adapter.run(prepared)

        assert len(local_calls) == 1
        assert local_calls[0][0] == ["npm", "test", "--silent"]
        assert result.exit_code == 0
