"""craft/loop.py + craft/executor.py unit tests (M1).

Includes the fixture-repo deterministic convergence: a failing pytest suite
is turned green by an explicitly injected fix rule, with budget gates,
stuck detection, checkpoint resume and honest report artifacts.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

import pytest

from craft.budget import Budget
from craft.editor import Editor
from craft.executor import (
    CommandNotAllowedError,
    Executor,
    extract_pytest_failed_tests,
)
from craft.loop import CraftLoop, CraftLoopError
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"


def write_fixture_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
        '    return "hello " + name\n',
        encoding="utf-8",
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
    )


def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    assert step.id == "s3"
    assert "预期" in diagnosis
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def noop_fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x / 2")
    return ["calc.py"]


def run_loop(
    tmp_path: Path,
    fix_registry: dict[str, object],
    *,
    job_id: str = "job-1",
    budget: Budget | None = None,
    started_at: float | None = None,
) -> tuple[CraftLoop, dict[str, object]]:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id=job_id,
        fix_registry=fix_registry,
        exec_mode="local",
        budget=budget,
        started_at=started_at,
    )
    return loop, loop.run()


def test_loop_converges_done_with_injected_fix(tmp_path: Path) -> None:
    loop, report = run_loop(tmp_path, {"test": fix_double})
    assert report["result"] == "DONE"
    assert report["mode"] == "deterministic"
    assert report["self_verify"]["status"] == "not_implemented"
    assert report["budget_used"]["tokens"] == 0
    assert report["budget_used"]["iterations"] <= loop.budget.max_iterations
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
    steps = {step["id"]: step for step in report["steps"]}
    assert all(steps[sid]["status"] == "green" for sid in ("s1", "s2", "s3", "s4"))
    assert steps["s3"]["iterations"] == 1
    assert steps["s3"]["evidence"]["check"] == "test_green"
    assert steps["s3"]["evidence"]["exit_code"] == 0
    assert report["diff_stat"]["files_changed"] == 1
    assert report["diff_stat"]["files"] == ["calc.py"]
    artifact = loop.artifact_dir
    assert artifact.is_dir()
    assert (artifact / "report.json").is_file()
    assert (artifact / "plan.json").is_file()
    assert (artifact / "checkpoint.json").is_file()
    assert (artifact / "audit.jsonl").is_file()
    checkpoint = json.loads((artifact / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["job_id"] == loop.job_id
    assert checkpoint["last_green_step"] == "s4"
    entries_s3 = [entry for entry in checkpoint["entries"] if entry["step_id"] == "s3"]
    assert len(entries_s3) == 1
    iteration = entries_s3[0]
    assert iteration["verdict"] == "green"
    assert iteration["iteration"] == 1
    assert iteration["edits_applied"] == ["calc.py"]
    assert "预期" in iteration["diagnosis"]
    assert iteration["build_result"]["exit_code"] == 0


def test_loop_no_fix_rule_fails_honestly(tmp_path: Path) -> None:
    _loop, report = run_loop(tmp_path, {})
    assert report["result"] == "FAILED"
    steps = {step["id"]: step for step in report["steps"]}
    assert steps["s3"]["status"] == "failed"
    assert "fix 规则" in steps["s3"]["evidence"]["reason"]
    assert "return x / 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


def test_loop_same_error_three_times_stuck(tmp_path: Path) -> None:
    _loop, report = run_loop(tmp_path, {"test": noop_fix})
    assert report["result"] == "STUCK"
    steps = {step["id"]: step for step in report["steps"]}
    assert steps["s3"]["status"] == "stuck"
    assert steps["s3"]["iterations"] == 3
    assert "连续 3 次" in steps["s3"]["evidence"]["reason"]


def test_loop_iteration_budget_exceeded_fails(tmp_path: Path) -> None:
    budget = Budget(max_iterations=1)
    _loop, report = run_loop(tmp_path, {"test": noop_fix}, budget=budget)
    assert report["result"] == "FAILED"
    steps = {step["id"]: step for step in report["steps"]}
    assert "迭代预算超限" in steps["s3"]["evidence"]["reason"]
    assert report["budget_used"]["iterations"] == 1


def test_loop_time_budget_expired_honest(tmp_path: Path) -> None:
    _loop, report = run_loop(tmp_path, {}, started_at=time.time() - 3600.0)
    assert report["result"] == "EXPIRED"
    assert "时间预算超限" in report["steps"][0]["evidence"]["reason"]


def test_loop_resume_from_checkpoint_continues(tmp_path: Path) -> None:
    loop, first = run_loop(tmp_path, {}, job_id="job-r")
    assert first["result"] == "FAILED"
    resumed = CraftLoop.from_checkpoint(
        loop.artifact_dir, fix_registry={"test": fix_double}, exec_mode="local"
    )
    report = resumed.run()
    assert report["result"] == "DONE"
    assert report["job_id"] == "job-r"
    steps = {step["id"]: step for step in report["steps"]}
    assert steps["s1"]["status"] == "green" and steps["s1"]["evidence"].get("resumed") is True
    assert steps["s2"]["status"] == "green" and steps["s2"]["evidence"].get("resumed") is True
    assert steps["s3"]["status"] == "green" and not steps["s3"]["evidence"].get("resumed")
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


def test_loop_rejects_non_deterministic_plan(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    llm_plan = dataclasses.replace(plan, mode="llm")
    with pytest.raises(CraftLoopError, match="deterministic"):
        CraftLoop(spec, llm_plan, tmp_path, exec_mode="local")


# -- executor -----------------------------------------------------------


def test_executor_rejects_non_whitelisted_command(tmp_path: Path) -> None:
    with pytest.raises(CommandNotAllowedError, match="白名单"):
        Executor(tmp_path, mode="local").run(["rm", "-rf", "/"])


def test_executor_runs_whitelisted_python_locally(tmp_path: Path) -> None:
    result = Executor(tmp_path, mode="local").run(
        [sys.executable, "-c", "print('specproof-craft-ok')"]
    )
    assert result.exit_code == 0
    assert result.mode == "local"
    assert "specproof-craft-ok" in result.stdout


def test_executor_truncates_output_to_tail_4000(tmp_path: Path) -> None:
    code = "import sys\nsys.stdout.write('x' * 9000)"
    result = Executor(tmp_path, mode="local").run([sys.executable, "-c", code])
    assert result.truncated is True
    assert len(result.output_tail) == 4000
    assert result.output_tail == "x" * 4000
    assert len(result.stdout) == 9000


def test_executor_extra_commands_via_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform == "win32":
        extra, command = "cmd", ["cmd", "/c", "echo", "craft-echo-ok"]
    else:
        extra, command = "echo", ["echo", "craft-echo-ok"]
    monkeypatch.setenv("CRAFT_EXTRA_COMMANDS", extra)
    result = Executor(tmp_path, mode="local").run(command)
    assert result.exit_code == 0
    assert "craft-echo-ok" in result.stdout


def test_executor_parses_surefire_xml_failures(tmp_path: Path) -> None:
    reports = tmp_path / "target" / "surefire-reports"
    reports.mkdir(parents=True)
    (reports / "TEST-com.demo.FooTest.xml").write_text(
        '<?xml version="1.0"?>\n'
        '<testsuite name="com.demo.FooTest">\n'
        '  <testcase name="test_boom" classname="com.demo.FooTest" time="0.1">\n'
        '    <failure message="expected 8 got 2">java.lang.AssertionError: expected 8 got 2\n'
        "\tat com.demo.FooTest.test_boom(FooTest.java:12)\n"
        "\tat org.junit.platform.commons.util."
        "ReflectionUtils.invokeMethod(ReflectionUtils.java:725)\n"
        "    </failure>\n"
        "  </testcase>\n"
        '  <testcase name="test_ok" classname="com.demo.FooTest" time="0.0"/>\n'
        "</testsuite>\n",
        encoding="utf-8",
    )
    report = Executor(tmp_path, mode="local").parse_test_results()
    assert report.reports_found == 1
    assert len(report.failed_tests) == 1
    failed = report.failed_tests[0]
    assert failed.name == "test_boom"
    assert failed.classname == "com.demo.FooTest"
    assert failed.message == "expected 8 got 2"
    assert 1 <= len(failed.stack_lines) <= 5
    assert "AssertionError" in failed.stack_lines[0]


def test_executor_missing_surefire_xml_is_honest_empty(tmp_path: Path) -> None:
    report = Executor(tmp_path, mode="local").parse_test_results()
    assert report.reports_found == 0
    assert report.failed_tests == []
    assert "未找到" in report.note


def test_extract_pytest_failed_tests_from_output() -> None:
    output = "FAILED test_calc.py::test_double - assert 2.0 == 8\n1 failed, 1 passed\n"
    assert extract_pytest_failed_tests(output) == ["test_calc.py::test_double"]
