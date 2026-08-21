"""Unit tests — execution adapter protocol + compatibility matrix (Q lane).

Covers guide §4.5 task 10: detect rules, registry order, prepare command
shape (offline/test-injection flags), run through the sandbox (mocked),
collect evidence fields, AdapterNotImplemented for planned adapters, and
the compatibility matrix content (code rows + rendered document).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from experiments.adapters import (
    AdapterNotImplemented,
    EvidenceFragment,
    ExecutionAdapter,
    ExecutionRequest,
    JavaMavenAdapter,
    RepositorySnapshot,
    registry,
)
from sandbox.runner import DEFAULT_IMAGE, SandboxResult

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_DOC = REPO_ROOT / "docs" / "architecture" / "EXECUTION_COMPATIBILITY.md"


def _make_repo(tmp_path: Path, *, pom: bool = True, src: bool = True) -> Path:
    if pom:
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    if src:
        java_dir = tmp_path / "src" / "main" / "java"
        java_dir.mkdir(parents=True)
        (java_dir / "Placeholder.java").write_text("class Placeholder {}", encoding="utf-8")
    return tmp_path


def _fake_sandbox_result(**overrides: Any) -> SandboxResult:
    kwargs: dict[str, Any] = {
        "exit_code": 0,
        "stdout": (
            "Tests run: 3, Failures: 1, Errors: 0, Skipped: 0\n"
            "BUILD SUCCESS\n"
        ),
        "stderr": "",
        "mode": "docker",
    }
    kwargs.update(overrides)
    return SandboxResult(**kwargs)


class TestDetectRules:
    def test_java_maven_hit_requires_pom_and_src_main_java(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        adapter = registry.get(RepositorySnapshot(path=str(repo)))
        assert isinstance(adapter, JavaMavenAdapter)
        profile = adapter.detect(RepositorySnapshot(path=str(repo)))
        assert profile.language == "java"
        assert profile.build_tool == "maven"
        assert profile.test_runner == "junit5 + maven-surefire"
        assert profile.known_limits

    def test_no_pom_is_rejected_fail_closed(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, pom=False)
        with pytest.raises(AdapterNotImplemented) as excinfo:
            registry.get(RepositorySnapshot(path=str(repo)))
        assert "no execution adapter matched" in str(excinfo.value)

    def test_pom_without_src_main_java_is_rejected(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, src=False)
        with pytest.raises(AdapterNotImplemented):
            registry.get(RepositorySnapshot(path=str(repo)))

    def test_files_snapshot_shortcut(self) -> None:
        snapshot = RepositorySnapshot(path="", files=("pom.xml", "src/main/java"))
        assert isinstance(registry.get(snapshot), JavaMavenAdapter)


class TestRegistryOrder:
    def test_java_maven_is_first_registered(self) -> None:
        assert isinstance(registry.adapters[0], JavaMavenAdapter)

    def test_planned_adapters_raise_adapter_not_implemented(self, tmp_path: Path) -> None:
        gradle_repo = tmp_path
        (gradle_repo / "build.gradle").write_text("", encoding="utf-8")
        with pytest.raises(AdapterNotImplemented) as excinfo:
            registry.get(RepositorySnapshot(path=str(gradle_repo)))
        assert "planned" in str(excinfo.value)

    def test_planned_adapter_prepare_raises(self) -> None:
        planned = registry.adapters[1]
        with pytest.raises(AdapterNotImplemented, match="planned"):
            planned.prepare(ExecutionRequest(workspace="ws", goal="run_test"))

    def test_java_maven_satisfies_protocol(self) -> None:
        assert isinstance(JavaMavenAdapter(), ExecutionAdapter)


class TestPrepareCommandShape:
    def _prepared(self, tmp_path: Path, **req: Any) -> Any:
        adapter = JavaMavenAdapter()
        return adapter.prepare(ExecutionRequest(workspace=str(tmp_path), **req))

    def test_run_test_command_offline_and_injection(self, tmp_path: Path) -> None:
        prepared = self._prepared(
            tmp_path, goal="run_test", test_class="SpecProofGeneratedTest", timeout=900
        )
        assert prepared.command == [
            "mvn", "-o", "test", "-q",
            "-Dtest=SpecProofGeneratedTest",
            "-DfailIfNoTests=false",
            "-f", "/work/pom.xml",
        ]
        assert prepared.timeout == 900
        # Offline flag is on the SANDBOX command (network is cut there).
        assert "-o" in prepared.command
        # Local fallback uses the wrapper with an absolute path.
        local_head = Path(prepared.local_command[0])
        assert local_head.name in ("mvnw", "mvnw.cmd")
        assert local_head.parent == tmp_path
        assert "-Dtest=SpecProofGeneratedTest" in prepared.local_command
        assert "-DfailIfNoTests=false" in prepared.local_command

    def test_skip_main_flag_reaches_both_commands(self, tmp_path: Path) -> None:
        prepared = self._prepared(
            tmp_path, goal="run_test", test_class="SpecProofGeneratedTest", skip_main=True
        )
        assert prepared.command[-1] == "-Dmaven.main.skip=true"
        assert prepared.local_command[-1] == "-Dmaven.main.skip=true"

    def test_test_compile_command_shape(self, tmp_path: Path) -> None:
        prepared = self._prepared(tmp_path, goal="test_compile")
        assert prepared.command == ["mvn", "-o", "test-compile", "-q", "-f", "/work/pom.xml"]
        assert prepared.timeout == 600

    def test_unknown_goal_fails_closed(self, tmp_path: Path) -> None:
        with pytest.raises(AdapterNotImplemented, match="unsupported Maven goal"):
            self._prepared(tmp_path, goal="deploy")

    def test_declared_image_digest_toolchain(self, tmp_path: Path) -> None:
        prepared = self._prepared(tmp_path, goal="test_compile")
        assert prepared.image == "maven:3.9-eclipse-temurin-21"
        assert prepared.image == DEFAULT_IMAGE
        assert prepared.image_digest.startswith("sha256:")
        assert "Maven 3.9.9" in JavaMavenAdapter.TOOLCHAIN
        assert "specproof-maven-cache-1000" in prepared.offline_policy
        assert "RUNBOOK" in prepared.offline_policy


class TestRunThroughSandbox:
    def test_run_delegates_to_run_sandboxed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import experiments.adapters as adapters

        calls: list[dict[str, Any]] = []

        def fake_run_sandboxed(
            command: list[str], workspace: str, timeout: int,
            mode: str | None, local_command: list[str],
        ) -> SandboxResult:
            calls.append({
                "command": command, "workspace": workspace, "timeout": timeout,
                "mode": mode, "local_command": local_command,
            })
            return _fake_sandbox_result()

        monkeypatch.setattr(adapters, "run_sandboxed", fake_run_sandboxed)
        adapter = JavaMavenAdapter()
        prepared = adapter.prepare(
            ExecutionRequest(workspace=str(tmp_path), goal="run_test", test_class="T")
        )
        result = adapter.run(prepared)

        assert len(calls) == 1
        assert calls[0]["command"] == prepared.command
        assert calls[0]["workspace"] == str(tmp_path)
        assert calls[0]["timeout"] == prepared.timeout
        assert calls[0]["mode"] is None
        assert calls[0]["local_command"] == prepared.local_command
        assert result.exit_code == 0
        assert result.mode == "docker"
        assert "BUILD SUCCESS" in result.stdout_tail
        assert result.sandbox_resources["network"] == "none"
        assert prepared.result is result

    def test_run_propagates_sandbox_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import experiments.adapters as adapters

        monkeypatch.setattr(
            adapters, "run_sandboxed",
            lambda *args, **kwargs: _fake_sandbox_result(exit_code=-1, stdout="", error="boom"),
        )
        adapter = JavaMavenAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(tmp_path), goal="test_compile"))
        result = adapter.run(prepared)
        assert result.error == "boom"
        assert result.exit_code == -1

    def test_output_tail_capped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import experiments.adapters as adapters

        big = (
            "x" * (adapters.OUTPUT_TAIL_CHARS + 10)
            + "Tests run: 1, Failures: 0, Errors: 0, Skipped: 0\n"
        )
        monkeypatch.setattr(
            adapters, "run_sandboxed",
            lambda *args, **kwargs: _fake_sandbox_result(stdout=big),
        )
        adapter = JavaMavenAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(tmp_path), goal="test_compile"))
        result = adapter.run(prepared)
        assert len(result.stdout_tail) <= adapters.OUTPUT_TAIL_CHARS
        assert "Tests run: 1" in result.stdout_tail


class TestCollectEvidence:
    def test_collect_after_run_returns_surefire_refs_and_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import experiments.adapters as adapters

        monkeypatch.setattr(
            adapters, "run_sandboxed",
            lambda *args, **kwargs: _fake_sandbox_result(),
        )
        adapter = JavaMavenAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(tmp_path), goal="test_compile"))
        adapter.run(prepared)
        fragment = adapter.collect(prepared)
        assert isinstance(fragment, EvidenceFragment)
        assert any("surefire-reports" in ref for ref in fragment.test_report_refs)
        assert any("SpecProofGeneratedTest.xml" in ref for ref in fragment.test_report_refs)
        assert fragment.exit_evidence["exit_code"] == 0
        assert fragment.exit_evidence["mode"] == "docker"
        assert fragment.exit_evidence["test_counts"] == {
            "tests": 3, "failures": 1, "errors": 0, "skipped": 0,
        }
        assert fragment.exit_evidence["sandbox_resources"]["network"] == "none"

    def test_collect_before_run_reports_not_collected(self, tmp_path: Path) -> None:
        adapter = JavaMavenAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(tmp_path), goal="test_compile"))
        fragment = adapter.collect(prepared)
        assert fragment.exit_evidence == {"exit_code": None, "collected": False}

    def test_cleanup_keeps_workspace(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        adapter = JavaMavenAdapter()
        prepared = adapter.prepare(ExecutionRequest(workspace=str(repo), goal="test_compile"))
        assert adapter.cleanup(prepared) is None
        assert (repo / "pom.xml").exists(), "cleanup must never delete the workspace"


class TestNodeWiring:
    def test_run_generated_test_goes_through_adapter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import experiments.adapters as adapters
        from agent.nodes.run_differential import _run_generated_test

        captured: list[list[str]] = []

        def fake_run_sandboxed(command: list[str], **kwargs: Any) -> SandboxResult:
            captured.append(command)
            return _fake_sandbox_result()

        monkeypatch.setattr(adapters, "run_sandboxed", fake_run_sandboxed)
        repo = _make_repo(tmp_path)
        result = _run_generated_test(str(repo), "SpecProofGeneratedTest")

        assert captured, "the node must execute through the adapter -> sandbox"
        assert "-o" in captured[0]
        assert "-Dtest=SpecProofGeneratedTest" in captured[0]
        assert result["exit_code"] == 0
        assert result["sandbox_mode"] == "docker"
        assert result["test_counts"] == {"tests": 3, "failures": 1, "errors": 0, "skipped": 0}
        assert result["error"] == ""

    def test_run_generated_test_keeps_no_pom_message(self, tmp_path: Path) -> None:
        from agent.nodes.run_differential import _run_generated_test

        result = _run_generated_test(str(tmp_path), "SpecProofGeneratedTest")
        assert result["error"] == "No pom.xml found"
        assert result["exit_code"] == -1

    def test_run_generated_test_unsupported_repo_fails_closed(self, tmp_path: Path) -> None:
        from agent.nodes.run_differential import _run_generated_test

        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        result = _run_generated_test(str(tmp_path), "SpecProofGeneratedTest")
        assert "detect rule" in result["error"]
        assert result["exit_code"] == -1

    def test_compile_test_goes_through_adapter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import experiments.adapters as adapters
        from agent.nodes.generate_counterexamples import _compile_test

        captured: list[list[str]] = []

        def fake_run_sandboxed(command: list[str], **kwargs: Any) -> SandboxResult:
            captured.append(command)
            return _fake_sandbox_result(stderr="", stdout="")

        monkeypatch.setattr(adapters, "run_sandboxed", fake_run_sandboxed)
        repo = _make_repo(tmp_path)
        exit_code, stderr = _compile_test(str(repo), "SpecProofGeneratedTest.java")
        assert captured, "the compile must execute through the adapter -> sandbox"
        assert captured[0][:4] == ["mvn", "-o", "test-compile", "-q"]
        assert exit_code == 0
        assert stderr == ""


class TestCompatibilityMatrixContent:
    def test_code_matrix_statuses(self) -> None:
        rows = registry.matrix()
        assert len(rows) == 5
        assert rows[0].language == "Java"
        assert rows[0].build_tool == "Maven"
        assert rows[0].status == "已支持 (实测)"
        assert rows[0].image_digest.startswith("sha256:")
        planned_rows = [row for row in rows[1:] if row.language != "Python"]
        assert all(row.status == "规划 (planned)" for row in planned_rows)
        planned_build_tools = {row.build_tool for row in planned_rows}
        assert planned_build_tools == {"Gradle", "npm", "go build"}
        python_row = next(row for row in rows if row.language == "Python")
        assert python_row.build_tool == "pip"
        assert python_row.test_runner == "pytest"
        assert python_row.status == "已支持 (local-first)"

    def test_matrix_document_declares_everything(self) -> None:
        text = MATRIX_DOC.read_text(encoding="utf-8")
        assert "不支持" in text and "任意项目" in text, "must refuse arbitrary projects"
        assert "已支持 (实测)" in text
        assert "规划 (planned)" in text
        assert "maven:3.9-eclipse-temurin-21" in text
        assert "sha256:c07f7ccfb8ca6c9fa29ee523f00afa7d2ca6132c92f8652c4aebb5ee3491f502" in text
        assert "specproof-maven-cache-1000" in text
        assert "RUNBOOK" in text
        assert "seed_sandbox_cache.ps1" in text
        # The four required declaration columns of guide §4.5.
        for header in ("镜像", "工具链", "离线策略", "已知限制", "支持状态"):
            assert header in text, f"matrix column {header} missing"
        # The five planned adapter families are named in the document.
        for name in ("Gradle", "npm", "Python", "Go"):
            assert name in text

    def test_adapter_declarations_match_matrix_doc(self) -> None:
        text = MATRIX_DOC.read_text(encoding="utf-8")
        assert JavaMavenAdapter.IMAGE in text
        assert JavaMavenAdapter.IMAGE_DIGEST in text
        assert JavaMavenAdapter.TOOLCHAIN.split(" / ")[0] in text


def test_detect_functions_exist_for_planned_adapters() -> None:
    from experiments import adapters as adapters

    for fn in (
        adapters.detect_java_gradle, adapters.detect_node,
        adapters.detect_go,
    ):
        with pytest.raises(AdapterNotImplemented, match="planned"):
            fn(RepositorySnapshot(path="."))

