"""Unit tests — Python/pytest adapter (local-first, 工业化指南 阶段 4 / W57).

Covers detect rules (pyproject.toml | requirements.txt | pytest.ini, exotic
projects fail closed), prepare venv reuse/create plus honest
venv_create/pip_install failure classification, run through a fake local
runner, pytest summary parsing and output-tail truncation, collect
evidence, SPECPROOF_KEEP_VENV cleanup, and registry wiring. All subprocess
and filesystem effects are faked — no network, no real venv is created.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

import experiments.adapters as adapters
from experiments.adapters import (
    AdapterNotImplemented,
    ExecutionAdapter,
    ExecutionRequest,
    JavaMavenAdapter,
    LocalRunResult,
    PythonAdapter,
    PythonEnvironmentError,
    RepositorySnapshot,
    registry,
)

MATRIX_DOC = (
    Path(__file__).resolve().parents[2] / "docs" / "architecture" / "EXECUTION_COMPATIBILITY.md"
)


def _make_python_repo(tmp_path: Path, marker: str = "pyproject.toml") -> Path:
    (tmp_path / marker).write_text("", encoding="utf-8")
    return tmp_path


def _fake_run_ok(stdout: str = "3 passed in 0.01s\n", **overrides: Any) -> LocalRunResult:
    kwargs: dict[str, Any] = {"exit_code": 0, "stdout": stdout, "stderr": ""}
    kwargs.update(overrides)
    return LocalRunResult(**kwargs)


def _write_fake_venv(workspace: Path) -> Path:
    python = adapters._venv_python(workspace / PythonAdapter.VENV_DIR)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    return python


class TestDetectRules:
    def test_pyproject_toml_matches(self, tmp_path: Path) -> None:
        repo = _make_python_repo(tmp_path)
        adapter = registry.get(RepositorySnapshot(path=str(repo)))
        assert isinstance(adapter, PythonAdapter)
        profile = adapter.detect(RepositorySnapshot(path=str(repo)))
        assert profile.language == "python"
        assert profile.build_tool == "pip"
        assert profile.test_runner == "pytest"
        assert profile.known_limits

    def test_requirements_txt_matches(self, tmp_path: Path) -> None:
        repo = _make_python_repo(tmp_path, marker="requirements.txt")
        assert isinstance(registry.get(RepositorySnapshot(path=str(repo))), PythonAdapter)

    def test_pytest_ini_matches(self, tmp_path: Path) -> None:
        repo = _make_python_repo(tmp_path, marker="pytest.ini")
        assert isinstance(registry.get(RepositorySnapshot(path=str(repo))), PythonAdapter)

    def test_exotic_python_project_is_not_implemented(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").write_text("", encoding="utf-8")
        (tmp_path / "tox.ini").write_text("", encoding="utf-8")
        with pytest.raises(AdapterNotImplemented, match="no execution adapter matched"):
            registry.get(RepositorySnapshot(path=str(tmp_path)))
        with pytest.raises(AdapterNotImplemented, match="detect rule"):
            PythonAdapter().detect(RepositorySnapshot(path=str(tmp_path)))

    def test_files_snapshot_shortcut(self) -> None:
        snapshot = RepositorySnapshot(path="", files=("src", "pytest.ini"))
        assert isinstance(registry.get(snapshot), PythonAdapter)

    def test_java_repo_still_wins_registration_order(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "Placeholder.java").write_text("class Placeholder {}", encoding="utf-8")
        assert isinstance(registry.get(RepositorySnapshot(path=str(tmp_path))), JavaMavenAdapter)


class TestPrepare:
    def test_reuses_existing_venv_without_any_setup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        python = _write_fake_venv(tmp_path)
        calls: list[list[str]] = []

        def fake_run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
            calls.append(command)
            return _fake_run_ok()

        monkeypatch.setattr(adapters, "_run_local", fake_run_local)
        prepared = PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        assert calls == [], "reusing .venv must not invoke any subprocess"
        assert prepared.command == [str(python), "-m", "pytest", "-q"]
        assert prepared.local_command == prepared.command
        assert prepared.image == "—"
        assert prepared.image_digest == "—"
        assert prepared.timeout == 600
        assert "local-first" in prepared.offline_policy

    def test_creates_venv_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        calls: list[list[str]] = []

        def fake_run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
            calls.append(command)
            return _fake_run_ok(stdout="")

        monkeypatch.setattr(adapters, "_run_local", fake_run_local)
        prepared = PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        assert len(calls) == 1
        venv_call = calls[0]
        assert venv_call[0] == sys.executable
        assert venv_call[1:3] == ["-m", "venv"]
        assert venv_call[3] == str(tmp_path / PythonAdapter.VENV_DIR)
        python = adapters._venv_python(tmp_path / PythonAdapter.VENV_DIR)
        assert prepared.command == [str(python), "-m", "pytest", "-q"]

    def test_fresh_venv_installs_requirements(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        (tmp_path / "requirements.txt").write_text("pytest>=8\n", encoding="utf-8")
        calls: list[list[str]] = []

        def fake_run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
            calls.append(command)
            return _fake_run_ok(stdout="")

        monkeypatch.setattr(adapters, "_run_local", fake_run_local)
        PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        assert len(calls) == 2
        assert calls[0][1:3] == ["-m", "venv"]
        pip_call = calls[1]
        python = adapters._venv_python(tmp_path / PythonAdapter.VENV_DIR)
        assert pip_call[0] == str(python)
        assert pip_call[1:3] == ["-m", "pip"]
        assert "--disable-pip-version-check" in pip_call
        assert pip_call[-2:] == ["-r", str(tmp_path / "requirements.txt")]

    def test_test_class_becomes_k_selector(self, tmp_path: Path) -> None:
        repo = _make_python_repo(tmp_path)
        python = _write_fake_venv(tmp_path)
        prepared = PythonAdapter().prepare(
            ExecutionRequest(workspace=str(repo), goal="run_test", test_class="SpecProofTest")
        )
        assert prepared.command == [str(python), "-m", "pytest", "-q", "-k", "SpecProofTest"]

    def test_unsupported_goal_fails_closed(self, tmp_path: Path) -> None:
        repo = _make_python_repo(tmp_path)
        with pytest.raises(AdapterNotImplemented, match="run_test"):
            PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="test_compile"))


class TestEnvironmentFailures:
    def test_venv_create_failure_is_classified(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)

        def fake_run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
            return LocalRunResult(exit_code=1, stdout="", stderr="venv boom")

        monkeypatch.setattr(adapters, "_run_local", fake_run_local)
        with pytest.raises(PythonEnvironmentError) as excinfo:
            PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        assert excinfo.value.stage == "venv_create"
        assert "venv boom" in str(excinfo.value)

    def test_pip_install_failure_is_classified(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

        def fake_run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
            if command[1:3] == ["-m", "venv"]:
                return _fake_run_ok(stdout="")
            return LocalRunResult(
                exit_code=2, stdout="", stderr="ERROR: No matching distribution"
            )

        monkeypatch.setattr(adapters, "_run_local", fake_run_local)
        with pytest.raises(PythonEnvironmentError) as excinfo:
            PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        assert excinfo.value.stage == "pip_install"
        assert "No matching distribution" in str(excinfo.value)


class TestRunThroughLocalRunner:
    def test_run_delegates_to_local_runner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        _write_fake_venv(tmp_path)
        calls: list[dict[str, Any]] = []

        def fake_run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
            calls.append({"command": command, "cwd": cwd, "timeout": timeout})
            return _fake_run_ok()

        monkeypatch.setattr(adapters, "_run_local", fake_run_local)
        adapter = PythonAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        result = adapter.run(prepared)

        assert len(calls) == 1
        assert calls[0]["command"] == prepared.command
        assert calls[0]["cwd"] == str(tmp_path)
        assert calls[0]["timeout"] == 600
        assert result.exit_code == 0
        assert result.mode == "local"
        assert "3 passed" in result.stdout_tail
        assert result.sandbox_resources["sandbox"] == "none (local-first execution on the host)"
        assert prepared.result is result

    def test_output_tail_capped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        _write_fake_venv(tmp_path)
        big = "x" * (adapters.OUTPUT_TAIL_CHARS + 10) + "3 passed in 0.01s\n"
        monkeypatch.setattr(adapters, "_run_local", lambda *a, **k: _fake_run_ok(stdout=big))
        adapter = PythonAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        result = adapter.run(prepared)
        assert len(result.stdout_tail) <= adapters.OUTPUT_TAIL_CHARS
        assert "3 passed" in result.stdout_tail

    def test_run_reports_timeout_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        _write_fake_venv(tmp_path)

        def fake_run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
            return LocalRunResult(exit_code=-1, stdout="", stderr="", error="timed out")

        monkeypatch.setattr(adapters, "_run_local", fake_run_local)
        adapter = PythonAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        result = adapter.run(prepared)
        assert result.exit_code == -1
        assert "timed out" in result.error


class TestCollectEvidence:
    def test_collect_after_run_returns_pytest_counts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = _make_python_repo(tmp_path)
        _write_fake_venv(tmp_path)
        monkeypatch.setattr(
            adapters, "_run_local",
            lambda *a, **k: _fake_run_ok(stdout="2 passed, 1 failed in 1.23s\n"),
        )
        adapter = PythonAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        adapter.run(prepared)
        fragment = adapter.collect(prepared)
        assert fragment.test_report_refs == ()
        assert fragment.exit_evidence["exit_code"] == 0
        assert fragment.exit_evidence["mode"] == "local"
        assert fragment.exit_evidence["test_counts"] == {
            "tests": 3, "passed": 2, "failed": 1, "skipped": 0, "errors": 0,
        }

    def test_collect_before_run_reports_not_collected(self, tmp_path: Path) -> None:
        repo = _make_python_repo(tmp_path)
        _write_fake_venv(tmp_path)
        prepared = PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        fragment = PythonAdapter().collect(prepared)
        assert fragment.exit_evidence == {"exit_code": None, "collected": False}
        assert fragment.test_report_refs == ()

    def test_parse_pytest_summary_defaults_and_skips(self) -> None:
        assert adapters.parse_pytest_summary("no tests ran in 0.01s") == {
            "tests": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0,
        }
        assert adapters.parse_pytest_summary("10 passed, 2 skipped in 5.00s") == {
            "tests": 10, "passed": 10, "failed": 0, "skipped": 2, "errors": 0,
        }


class TestCleanup:
    def test_cleanup_removes_venv_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SPECPROOF_KEEP_VENV", raising=False)
        repo = _make_python_repo(tmp_path)
        _write_fake_venv(tmp_path)
        prepared = PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        PythonAdapter().cleanup(prepared)
        assert not (tmp_path / PythonAdapter.VENV_DIR).exists()
        assert (tmp_path / "pyproject.toml").exists(), "cleanup must never delete the workspace"

    def test_cleanup_keeps_venv_when_env_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SPECPROOF_KEEP_VENV", "1")
        repo = _make_python_repo(tmp_path)
        _write_fake_venv(tmp_path)
        prepared = PythonAdapter().prepare(ExecutionRequest(workspace=str(repo), goal="run_test"))
        PythonAdapter().cleanup(prepared)
        assert (tmp_path / PythonAdapter.VENV_DIR).exists()


class TestRegistryAndMatrix:
    def test_python_adapter_registered_after_maven(self) -> None:
        assert isinstance(registry.adapters[0], JavaMavenAdapter)
        assert isinstance(registry.adapters[3], PythonAdapter)

    def test_python_adapter_satisfies_protocol(self) -> None:
        assert isinstance(PythonAdapter(), ExecutionAdapter)

    def test_matrix_row_python_is_supported_local_first(self) -> None:
        rows = registry.matrix()
        python_row = next(row for row in rows if row.language == "Python")
        assert python_row.build_tool == "pip"
        assert python_row.test_runner == "pytest"
        assert python_row.status == "已支持 (local-first)"
        assert python_row.image == "—"
        assert "network" in python_row.offline_policy
        assert any("venv_create" in limit for limit in python_row.known_limits)

    def test_matrix_document_declares_python_row(self) -> None:
        text = MATRIX_DOC.read_text(encoding="utf-8")
        assert "已支持 (local-first)" in text
        assert "PythonEnvironmentError" in text
        assert "SPECPROOF_KEEP_VENV" in text
