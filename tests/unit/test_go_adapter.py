"""Go adapter unit tests (Phase 2.6) — no Docker required.

The lane contract mirrors Node/Python: container sandbox by default, no
host lane at all, offline module resolution from the seeded cache volume,
and a failed module download that runs NO tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import experiments.adapters as adapters
from experiments.adapters import (
    AdapterNotImplemented,
    ExecutionRequest,
    GoAdapter,
    RepositorySnapshot,
    parse_go_test_summary,
    registry,
)
from sandbox.runner import GO_PROFILE, SandboxResult


def _make_go_repo(tmp_path: Path) -> Path:
    (tmp_path / "go.mod").write_text(
        "module example.com/m\n\ngo 1.23\n", encoding="utf-8",
    )
    return tmp_path


class TestGoDetect:
    def test_go_mod_matches(self, tmp_path: Path) -> None:
        repo = _make_go_repo(tmp_path)
        adapter = registry.get(RepositorySnapshot(path=str(repo)))
        assert isinstance(adapter, GoAdapter)
        profile = adapter.detect(RepositorySnapshot(path=str(repo)))
        assert profile.language == "go"
        assert profile.build_tool == "go"
        assert profile.known_limits

    def test_no_go_mod_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AdapterNotImplemented, match="detect rule"):
            GoAdapter().detect(RepositorySnapshot(path=str(tmp_path)))

    def test_registered_after_python(self) -> None:
        assert isinstance(registry.adapters[-1], GoAdapter)


class TestGoPrepare:
    def test_prepare_is_pure_and_sandbox_shaped(self, tmp_path: Path) -> None:
        repo = _make_go_repo(tmp_path)
        prepared = GoAdapter().prepare(
            ExecutionRequest(workspace=str(repo), goal="run_test")
        )
        assert prepared.command == ["go", "test", "-json", "./..."]
        assert prepared.image == GoAdapter.IMAGE
        assert not (repo / ".gocache").exists(), (
            "prepare must have no host side effects"
        )

    def test_test_class_becomes_run_filter(self, tmp_path: Path) -> None:
        repo = _make_go_repo(tmp_path)
        prepared = GoAdapter().prepare(
            ExecutionRequest(
                workspace=str(repo), goal="run_test", test_class="TestX",
            )
        )
        assert prepared.command[-2:] == ["-run", "TestX"]

    def test_unsupported_goal_fails_closed(self, tmp_path: Path) -> None:
        repo = _make_go_repo(tmp_path)
        with pytest.raises(AdapterNotImplemented, match="run_test"):
            GoAdapter().prepare(
                ExecutionRequest(workspace=str(repo), goal="test_compile")
            )


class TestGoRun:
    def _recording_sandbox(
        self, monkeypatch: pytest.MonkeyPatch, fail_download: bool = False,
    ):
        calls: list[tuple[list[str], dict[str, Any]]] = []

        def fake_sandboxed(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            if fail_download and command[:2] == ["go", "build"]:
                return SandboxResult(
                    exit_code=1, stdout="",
                    stderr="go: missing go.sum entry; to add it:\n\tgo mod download",
                    mode="docker",
                )
            return SandboxResult(
                exit_code=0,
                stdout='{"Action":"pass","Package":"m","Test":"TestA"}\n'
                       '{"Action":"pass","Package":"m","Test":"TestB"}\n',
                stderr="",
                mode="docker",
            )

        monkeypatch.setattr(adapters, "run_sandboxed", fake_sandboxed)
        return calls

    def test_default_run_is_two_sandboxed_phases(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_go_repo(tmp_path)
        calls = self._recording_sandbox(monkeypatch)
        adapter = GoAdapter()
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(repo), goal="run_test")
        )
        result = adapter.run(prepared)

        assert len(calls) == 2
        download_cmd, download_kwargs = calls[0]
        test_cmd, test_kwargs = calls[1]
        assert download_cmd == GoAdapter.OFFLINE_VERIFY_COMMAND
        assert download_kwargs["profile"] is GO_PROFILE
        assert download_kwargs["mode"] == "docker"
        assert test_cmd[:3] == ["go", "test", "-json"]
        assert test_kwargs["profile"] is GO_PROFILE
        assert result.exit_code == 0
        assert result.sandbox_resources["setup_phase"] == "completed"
        assert result.sandbox_resources["network"].startswith("none")

    def test_download_failure_runs_no_tests(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_go_repo(tmp_path)
        calls = self._recording_sandbox(monkeypatch, fail_download=True)
        adapter = GoAdapter()
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(repo), goal="run_test")
        )
        result = adapter.run(prepared)

        assert len(calls) == 1, "a failed download must stop before tests"
        assert result.exit_code == 1
        assert "tests were not run" in result.error
        assert result.sandbox_resources["setup_phase"] == (
            "build_verify failed — tests not run"
        )

    def test_local_mode_is_refused_not_silently_run(
        self, tmp_path: Path,
    ) -> None:
        """No host lane exists for Go: a named local request is an honest
        refusal, never a silent host execution of untrusted test code."""
        repo = _make_go_repo(tmp_path)
        adapter = GoAdapter()
        prepared = adapter.prepare(
            ExecutionRequest(
                workspace=str(repo), goal="run_test", sandbox_mode="local",
            )
        )
        with pytest.raises(AdapterNotImplemented, match="no host lane"):
            adapter.run(prepared)


class TestGoTestSummaryParsing:
    def test_counts_per_test_actions(self) -> None:
        text = (
            '{"Action":"start","Package":"m"}\n'
            '{"Action":"run","Package":"m","Test":"TestA"}\n'
            '{"Action":"pass","Package":"m","Test":"TestA"}\n'
            '{"Action":"fail","Package":"m","Test":"TestB"}\n'
            '{"Action":"skip","Package":"m","Test":"TestC"}\n'
            '{"Action":"pass","Package":"m"}\n'
        )
        assert parse_go_test_summary(text) == {
            "tests": 3, "passed": 1, "failed": 1, "errors": 0,
        }

    def test_package_level_fail_counts_as_error_not_test_failure(self) -> None:
        text = (
            '{"Action":"fail","Package":"m/broken"}\n'
            '{"Action":"pass","Package":"m","Test":"TestA"}\n'
        )
        assert parse_go_test_summary(text) == {
            "tests": 1, "passed": 1, "failed": 0, "errors": 1,
        }

    def test_non_json_lines_are_skipped(self) -> None:
        text = "go: downloading example.com/x\n# example.com/m\nnot json\n"
        assert parse_go_test_summary(text) == {
            "tests": 0, "passed": 0, "failed": 0, "errors": 0,
        }


class TestGoSandboxProfile:
    def test_go_profile_carries_modcache_and_gocache_submount(self) -> None:
        from sandbox.runner import build_docker_argv

        argv = build_docker_argv(
            ["go", "mod", "download"], "/ws", GO_PROFILE,
        )
        assert argv[argv.index("--user") + 1] == "1000:1000"
        assert "--network" in argv and "none" in argv
        assert "/ws:/work:ro" in argv
        assert "/ws/.gocache:/work/.gocache" in argv
        assert "/ws/.gocache/tmp:/work/.gocache/tmp" in argv
        assert "specproof-go-modcache-1000:/go/pkg/mod" in argv
        assert "GOPROXY=off" in argv
        assert "GOTMPDIR=/work/.gocache/tmp" in argv
