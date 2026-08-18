"""craft/gates.py unit tests — layered gate composition (W34 task 7).

Covers the full contract:
  - every gate returns {gate, status, note, findings, duration_ms};
  - run_test / run_build / run_typecheck: detection, pass/fail mapping,
    skipped-with-honest-note when no object exists, error when the executor
    raises (never a fake pass);
  - security gate: real agent.security_scanner + canary sentinel, changed-file
    filtering, CRITICAL/HIGH block, MEDIUM recorded but non-blocking, scanner
    unavailable/raises -> skipped with a note;
  - self-verify gate: reuses craft.verify.self_verify verbatim + injected
    fakes for failed/skipped/error mapping;
  - composition: FAIL > SKIPPED > PASS, error is worst of all;
  - GatePipeline -> GateReport with a machine-greppable summary line.

All tests are local/fake — no network, no live LLM, no Docker. Every exec
gate runs through a scripted FakeRunner (an ExecRunner), never the sandbox.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

import agent.security_scanner
import craft.gates
from craft.executor import CommandNotAllowedError, ExecResult
from craft.gates import (
    GATE_ORDER,
    GatePipeline,
    GateReport,
    GateResult,
    compose_verdict,
    detect_test_suite,
    run_build_gate,
    run_test_gate,
    run_typecheck_gate,
    security_gate,
    self_verify_gate,
)
from craft.schemas import ChangeBundle
from craft.verify import CANARY_MARKER

FAKE_KEY_LINE = "API_" + 'KEY = "' + "sk-" + "abcdefghijklmnopqrstuvwxyz123456" + '"'
JWT_LINE = 'TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig_ABC123"'


class FakeRunner:
    """Scripted ExecRunner: pops (exit_code, output_tail) per run call."""

    def __init__(
        self, script: list[tuple[int, str]] | None = None, exc: Exception | None = None
    ) -> None:
        self.script = list(script or [])
        self.exc = exc
        self.calls: list[list[str]] = []

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult:
        self.calls.append(list(command))
        if self.exc is not None:
            raise self.exc
        if not self.script:
            exit_code, tail = 0, ""
        else:
            exit_code, tail = self.script.pop(0)
        return ExecResult(
            command=list(command),
            exit_code=exit_code,
            stdout=tail,
            stderr="",
            output_tail=tail,
            truncated=False,
            error="",
            mode="local",
        )


def make_bundle(files: list[str], task_id: str = "task-1") -> ChangeBundle:
    return ChangeBundle(task_id=task_id, changed_files=files)


def write_python_repo(tmp_path: Path, *, with_tests: bool = True) -> None:
    (tmp_path / "calc.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    if with_tests:
        (tmp_path / "test_calc.py").write_text(
            "from calc import double\n\n\ndef test_double():\n"
            "    assert double(4) == 8\n",
            encoding="utf-8",
        )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['.']\n", encoding="utf-8"
    )


def clean_pipeline(tmp_path: Path, runner: FakeRunner | None = None) -> GatePipeline:
    resolved = runner if runner is not None else FakeRunner([(0, ""), (0, ""), (0, "")])
    return GatePipeline(tmp_path, executor=resolved)


# -- result contract ---------------------------------------------------------


def test_gate_result_to_dict_has_exact_contract() -> None:
    result = GateResult("run_test", "passed", "note", [{"kind": "x"}], 12)
    assert result.to_dict() == {
        "gate": "run_test",
        "status": "passed",
        "note": "note",
        "findings": [{"kind": "x"}],
        "duration_ms": 12,
    }


def test_gate_report_summary_line_is_greppable() -> None:
    report = GateReport(
        task_id="t-1",
        entries=(GateResult("run_test", "passed", ""), GateResult("security", "skipped", "")),
        overall="skipped",
        overall_note="honest",
        duration_ms=3,
    )
    assert report.summary_line.startswith("GATES: ")
    assert "overall=skipped" in report.summary_line
    assert "run_test=passed" in report.summary_line
    assert "security=skipped" in report.summary_line
    assert report.to_dict()["summary"] == report.summary_line


# -- test suite detection ------------------------------------------------------


def test_detect_test_suite_finds_python_and_java(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    (tmp_path / "src" / "test" / "java").mkdir(parents=True)
    (tmp_path / "src" / "test" / "java" / "AccountControllerTest.java").write_text(
        "class AccountControllerTest {}\n", encoding="utf-8"
    )
    suite = detect_test_suite(tmp_path)
    assert "test_calc.py" in suite
    assert "src/test/java/AccountControllerTest.java" in suite


def test_detect_test_suite_skips_generated_dirs(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "test_ghost.py").write_text("", encoding="utf-8")
    assert detect_test_suite(tmp_path) == []


def test_detect_test_suite_empty_when_no_tests(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("x = 1\n", encoding="utf-8")
    assert detect_test_suite(tmp_path) == []


# -- Gate 1: run_test -----------------------------------------------------------


def test_run_test_gate_passes_with_fake_executor(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    runner = FakeRunner([(0, "")])
    result = run_test_gate(tmp_path, executor=runner)
    assert result.status == "passed"
    assert runner.calls == [["python", "-m", "pytest", "-q"]]
    assert result.duration_ms >= 0


def test_run_test_gate_fails_and_reports_findings(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    runner = FakeRunner([(1, "FAILED tests/unit/test_calc.py::test_double - assert 2 == 8")])
    result = run_test_gate(tmp_path, executor=runner)
    assert result.status == "failed"
    assert result.findings and result.findings[0]["kind"] == "run_test"
    assert "exit 1" in result.findings[0]["description"]
    assert "失败" in result.note


def test_run_test_gate_skipped_when_no_tests_detected(tmp_path: Path) -> None:
    write_python_repo(tmp_path, with_tests=False)
    result = run_test_gate(tmp_path, executor=FakeRunner())
    assert result.status == "skipped"
    assert "未检测到测试文件" in result.note
    assert result.findings == []


def test_run_test_gate_error_when_executor_raises(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    result = run_test_gate(
        tmp_path, executor=FakeRunner(exc=CommandNotAllowedError("命令被白名单拒绝"))
    )
    assert result.status == "error"
    assert "执行异常" in result.note
    assert "CommandNotAllowedError" in result.note


def test_run_test_gate_java_tests_without_pom_skipped(tmp_path: Path) -> None:
    (tmp_path / "AccountControllerTest.java").write_text(
        "class AccountControllerTest {}\n", encoding="utf-8"
    )
    result = run_test_gate(tmp_path, executor=FakeRunner())
    assert result.status == "skipped"
    assert "无 pom.xml" in result.note
    assert "不伪造通过" in result.note


def test_run_test_gate_runs_both_suites_when_java_has_pom(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (tmp_path / "AccountControllerTest.java").write_text(
        "class AccountControllerTest {}\n", encoding="utf-8"
    )
    runner = FakeRunner([(0, ""), (0, "")])
    result = run_test_gate(tmp_path, executor=runner)
    assert result.status == "passed"
    assert runner.calls == [["python", "-m", "pytest", "-q"], ["mvn", "-q", "test"]]


# -- Gate 2: run_build -----------------------------------------------------------


def test_run_build_gate_python_uses_compileall(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    runner = FakeRunner([(0, "")])
    result = run_build_gate(tmp_path, executor=runner)
    assert result.status == "passed"
    assert runner.calls == [["python", "-m", "compileall", "-q", "."]]
    assert "compileall" in result.note


def test_run_build_gate_maven_command(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    runner = FakeRunner([(0, "")])
    result = run_build_gate(tmp_path, executor=runner)
    assert result.status == "passed"
    assert runner.calls == [["mvn", "-q", "-DskipTests", "compile"]]


def test_run_build_gate_skipped_without_build_config(tmp_path: Path) -> None:
    result = run_build_gate(tmp_path, executor=FakeRunner())
    assert result.status == "skipped"
    assert "未检测到构建配置" in result.note


# -- Gate 3: run_typecheck --------------------------------------------------------


def test_run_typecheck_gate_mypy_on_changed_py_files(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    runner = FakeRunner([(1, "calc.py:1: error: Function is missing a return type annotation")])
    result = run_typecheck_gate(["calc.py", "notes.md"], tmp_path, executor=runner)
    assert result.status == "failed"
    assert runner.calls == [["python", "-m", "mypy", "calc.py"]]
    assert result.findings[0]["kind"] == "run_typecheck"


def test_run_typecheck_gate_skipped_without_py_changes(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    result = run_typecheck_gate(["notes.md"], tmp_path, executor=FakeRunner())
    assert result.status == "skipped"
    assert "无 .py" in result.note


def test_run_typecheck_gate_java_project_skipped_honestly(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    result = run_typecheck_gate(["AccountController.java"], tmp_path, executor=FakeRunner())
    assert result.status == "skipped"
    assert "Java 项目无独立 typecheck" in result.note


# -- Gate 4: security --------------------------------------------------------------


def test_security_gate_passes_on_clean_files(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    result = security_gate(["calc.py", "test_calc.py"], tmp_path)
    assert result.status == "passed"
    assert result.findings == []
    assert "无密钥/canary finding" in result.note


def test_security_gate_fails_on_secret_in_changed_file(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        FAKE_KEY_LINE + "\n\ndef double(x):\n    return x * 2\n", encoding="utf-8"
    )
    result = security_gate(["calc.py"], tmp_path)
    assert result.status == "failed"
    secrets = [f for f in result.findings if f["kind"] == "secret"]
    assert secrets and all(f["severity"] == "CRITICAL" for f in secrets)
    assert any(f["file"] == "calc.py" for f in secrets)
    assert "拦截" in result.note


def test_security_gate_fails_on_canary_sentinel(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        f'CANARY = "{CANARY_MARKER}a7f3b2c9d1e4_SECRET_DO_NOT_COMMIT"\n', encoding="utf-8"
    )
    result = security_gate(["calc.py"], tmp_path)
    assert result.status == "failed"
    canaries = [f for f in result.findings if f["kind"] == "canary"]
    assert len(canaries) == 1
    assert canaries[0]["severity"] == "CRITICAL"


def test_security_gate_filters_findings_outside_changed_set(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    (tmp_path / "other.txt").write_text(FAKE_KEY_LINE + "\n", encoding="utf-8")
    result = security_gate(["calc.py"], tmp_path)
    assert result.status == "passed"
    assert result.findings == []


def test_security_gate_medium_finding_recorded_not_blocking(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(JWT_LINE + "\n", encoding="utf-8")
    result = security_gate(["calc.py"], tmp_path)
    assert result.status == "passed"
    assert len(result.findings) == 1
    assert result.findings[0]["severity"] == "MEDIUM"
    assert "非阻塞" in result.note


def test_security_gate_skipped_when_no_changed_files(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    result = security_gate([], tmp_path)
    assert result.status == "skipped"
    assert "无改动文件" in result.note


def test_security_gate_scanner_unavailable_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "calc.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "agent.security_scanner", None)
    result = security_gate(["calc.py"], tmp_path)
    assert result.status == "skipped"
    assert "安全扫描不可用" in result.note


def test_security_gate_scanner_raises_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "calc.py").write_text("x = 1\n", encoding="utf-8")

    def boom(root: str) -> Any:
        raise RuntimeError("scanner boom")

    monkeypatch.setattr(agent.security_scanner, "scan_directory", boom)
    result = security_gate(["calc.py"], tmp_path)
    assert result.status == "skipped"
    assert "执行失败" in result.note
    assert "scanner boom" in result.note


def test_security_gate_injected_scan_callable_used(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("x = 1\n", encoding="utf-8")
    scanned: list[str] = []

    class FakeScan:
        def __init__(self, findings: list[Any]) -> None:
            self.findings = findings

    def fake_scan(root: str) -> FakeScan:
        scanned.append(root)
        return FakeScan([])

    result = security_gate(["calc.py"], tmp_path, scan=fake_scan)
    assert result.status == "passed"
    assert scanned == [str(tmp_path)]


# -- Gate 5: self_verify ------------------------------------------------------------


def test_self_verify_gate_reuses_real_verify(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    result = self_verify_gate(["calc.py", "test_calc.py"], tmp_path)
    assert result.status == "passed"
    assert "自校验通过" in result.note


def test_self_verify_gate_maps_failed_result(tmp_path: Path) -> None:
    def fake_verify(
        changed: list[str], workspace: Path, *, base_files: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return {"status": "failed", "findings": [{"kind": "contract"}], "note": "硬门"}

    result = self_verify_gate(["A.java"], tmp_path, verify_fn=fake_verify)
    assert result.status == "failed"
    assert result.findings == [{"kind": "contract"}]
    assert result.note == "硬门"


def test_self_verify_gate_injected_fn_raises_becomes_error(tmp_path: Path) -> None:
    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("verify boom")

    result = self_verify_gate(["calc.py"], tmp_path, verify_fn=boom)
    assert result.status == "error"
    assert "verify boom" in result.note


def test_self_verify_gate_unknown_status_becomes_error(tmp_path: Path) -> None:
    def weird(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": "unverifiable", "findings": [], "note": ""}

    result = self_verify_gate(["calc.py"], tmp_path, verify_fn=weird)
    assert result.status == "error"
    assert "未知 status" in result.note


# -- composition ---------------------------------------------------------------------


def make_entry(gate: str, status: str) -> GateResult:
    return GateResult(gate, status, "")


def test_compose_verdict_precedence() -> None:
    assert compose_verdict([make_entry("a", "passed")])[0] == "passed"
    assert compose_verdict(
        [make_entry("a", "passed"), make_entry("b", "skipped")]
    )[0] == "skipped"
    assert compose_verdict(
        [make_entry("a", "skipped"), make_entry("b", "failed")]
    )[0] == "failed"
    assert compose_verdict(
        [make_entry("a", "passed"), make_entry("b", "failed"), make_entry("c", "passed")]
    )[0] == "failed"
    status, note = compose_verdict(
        [make_entry("a", "passed"), make_entry("b", "error"), make_entry("c", "failed")]
    )
    assert status == "error"
    assert "b" in note


def test_compose_verdict_empty_is_error() -> None:
    status, note = compose_verdict([])
    assert status == "error"
    assert "未运行任何门禁" in note


# -- GatePipeline ---------------------------------------------------------------------


def test_pipeline_all_pass_and_machine_greppable_summary(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    report = clean_pipeline(tmp_path).run(make_bundle(["calc.py", "test_calc.py"]))
    assert report.overall == "passed"
    assert [entry.gate for entry in report.entries] == list(GATE_ORDER)
    assert all(entry.status == "passed" for entry in report.entries)
    assert report.summary_line.startswith("GATES: task=task-1 overall=passed")
    assert "security=passed" in report.summary_line
    assert "self_verify=passed" in report.summary_line
    assert report.to_dict()["overall"] == "passed"


def test_pipeline_failed_beats_skipped_and_passed(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    runner = FakeRunner([(1, "boom"), (0, ""), (0, "")])
    report = clean_pipeline(tmp_path, runner).run(make_bundle(["calc.py", "test_calc.py"]))
    assert report.overall == "failed"
    assert "run_test" in report.overall_note


def test_pipeline_skipped_beats_passed(tmp_path: Path) -> None:
    write_python_repo(tmp_path, with_tests=False)
    runner = FakeRunner([(0, ""), (0, "")])
    report = clean_pipeline(tmp_path, runner).run(make_bundle(["calc.py"]))
    assert report.overall == "skipped"
    assert report.entries[0].status == "skipped"
    assert "不认证为通过" in report.overall_note


def test_pipeline_error_is_worst_of_all(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    runner = FakeRunner(exc=CommandNotAllowedError("拒绝"))
    report = clean_pipeline(tmp_path, runner).run(make_bundle(["calc.py", "test_calc.py"]))
    assert report.overall == "error"
    assert any(entry.status == "error" for entry in report.entries[:3])
    assert "run_test" in report.overall_note


def test_pipeline_gate_exception_becomes_error_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_python_repo(tmp_path)

    def broken(workspace: Path, *, executor: Any = None) -> GateResult:
        raise RuntimeError("gate adapter boom")

    monkeypatch.setattr(craft.gates, "run_test_gate", broken)
    runner = FakeRunner([(0, ""), (0, "")])
    report = clean_pipeline(tmp_path, runner).run(make_bundle(["calc.py", "test_calc.py"]))
    assert report.overall == "error"
    run_test_entry = report.entries[0]
    assert run_test_entry.status == "error"
    assert "gate adapter boom" in run_test_entry.note
    assert any(entry.status == "passed" for entry in report.entries[1:3])


def test_pipeline_changed_files_override_reaches_typecheck(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    runner = FakeRunner([(0, ""), (0, ""), (0, "")])
    report = clean_pipeline(tmp_path, runner).run(
        make_bundle(["notes.md"]), changed_files=["calc.py", "test_calc.py"]
    )
    assert report.overall == "passed"
    typecheck_call = runner.calls[2]
    assert typecheck_call[0] == "python"
    assert "mypy" in typecheck_call
    assert "calc.py" in typecheck_call


def test_pipeline_empty_gates_reports_error(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    pipeline = GatePipeline(tmp_path, enabled_gates=())
    report = pipeline.run(make_bundle(["calc.py"]))
    assert report.overall == "error"
    assert "未运行任何门禁" in report.overall_note


def test_pipeline_rejects_unknown_gate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="未注册的门禁"):
        GatePipeline(tmp_path, enabled_gates=("run_test", "banana"))


def test_pipeline_base_files_flow_to_self_verify(tmp_path: Path) -> None:
    write_python_repo(tmp_path)
    seen: dict[str, Any] = {}

    def fake_verify(
        changed: list[str], workspace: Path, *, base_files: dict[str, str] | None = None
    ) -> dict[str, Any]:
        seen["base_files"] = base_files
        return {"status": "passed", "findings": [], "note": "注入"}

    pipeline = GatePipeline(
        tmp_path,
        executor=FakeRunner([(0, ""), (0, ""), (0, "")]),
        self_verify_fn=fake_verify,
    )
    report = pipeline.run(
        make_bundle(["calc.py", "test_calc.py"]), base_files={"calc.py": "base"}
    )
    assert report.overall == "passed"
    assert seen["base_files"] == {"calc.py": "base"}
