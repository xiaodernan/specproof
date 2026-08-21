"""SpecCraft M3 self-verify layer unit tests (SPECCRAFT_PLAN §4.5).

Covers craft/verify.py + the loop/CLI wiring:
  - secret leak / canary sentinel in a changed file -> failed + finding;
  - clean changed files -> passed; empty change set -> skipped;
  - MEDIUM secrets (JWT) are recorded but do not block the gate;
  - Java contract checkers: a real Base->Head regression fails the gate;
    checker unavailable / checker raises / scanner unavailable -> skipped
    with an honest note (never faked, never a crash);
  - loop integration: a DONE run with a leaked key is overridden to FAILED
    and the fix is NOT rolled back; skip_self_verify=True marks skipped;
  - CLI: --self-verify (default) runs the gate, --no-self-verify skips it.

All tests are local/mocked — no network, no live LLM, no live infra.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import agent.checkers
import agent.security_scanner
from cli.specproof.commands.craft import craft_cmd
from craft.editor import Editor
from craft.loop import CraftLoop
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from craft.verify import CANARY_MARKER, self_verify

FAKE_KEY_LINE = "API_" + 'KEY = "' + "sk-" + "abcdefghijklmnopqrstuvwxyz123456" + '"'
FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

JAVA_BASE = """@RestController
public class AccountController {
    @PostMapping("/email")
    @PreAuthorize("isAuthenticated()")
    public String changeEmail(String email) { return "ok"; }
}
"""

JAVA_HEAD = """@RestController
public class AccountController {
    @PostMapping("/email")
    public String changeEmail(String email) { return "ok"; }
}
"""


def write_fixture_repo(tmp_path: Path, *, calc_body: str | None = None) -> None:
    (tmp_path / "calc.py").write_text(
        calc_body
        if calc_body is not None
        else "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
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
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def run_loop(
    tmp_path: Path,
    fix_registry: dict[str, object],
    *,
    job_id: str = "job-1",
    skip_self_verify: bool = False,
) -> tuple[CraftLoop, dict[str, Any]]:
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id=job_id,
        fix_registry=fix_registry,
        exec_mode="local",
        skip_self_verify=skip_self_verify,
    )
    return loop, loop.run()


def write_fix_module(tmp_path: Path, name: str) -> Path:
    mod = tmp_path / name
    mod.write_text(
        "from craft.editor import Editor\n"
        "from craft.planner import Step\n\n\n"
        "def fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:\n"
        '    editor.apply_edit("calc.py", "return x / 2", "return x * 2")\n'
        '    return ["calc.py"]\n\n\n'
        "FIXES = {'test': fix}\n",
        encoding="utf-8",
    )
    return mod


# -- security layer ----------------------------------------------------------


def test_secret_leak_in_changed_file_fails(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        FAKE_KEY_LINE + "\n\ndef double(x):\n    return x * 2\n", encoding="utf-8"
    )
    result = self_verify(["calc.py"], tmp_path)
    assert result["status"] == "failed"
    secrets = [f for f in result["findings"] if f["kind"] == "secret"]
    assert secrets, result
    assert all(f["severity"] == "CRITICAL" for f in secrets)
    assert any(f["file"] == "calc.py" for f in secrets)
    assert "拦截" in result["note"]


def test_canary_marker_in_changed_file_fails(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        f"# planted sentinel\nCANARY = \"{CANARY_MARKER}a7f3b2c9d1e4_SECRET_DO_NOT_COMMIT\"\n",
        encoding="utf-8",
    )
    result = self_verify(["calc.py"], tmp_path)
    assert result["status"] == "failed"
    canaries = [f for f in result["findings"] if f["kind"] == "canary"]
    assert len(canaries) == 1
    assert canaries[0]["severity"] == "CRITICAL"
    assert canaries[0]["file"] == "calc.py"


def test_clean_python_changed_files_pass(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    result = self_verify(["calc.py", "test_calc.py"], tmp_path)
    assert result["status"] == "passed"
    assert result["findings"] == []
    assert "无 Java" in result["note"]


def test_empty_changed_files_skipped(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    result = self_verify([], tmp_path)
    assert result["status"] == "skipped"
    assert "无改动文件" in result["note"]


def test_jwt_medium_finding_recorded_but_gate_passes(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        'TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig_ABC123"\n',
        encoding="utf-8",
    )
    result = self_verify(["calc.py"], tmp_path)
    assert result["status"] == "passed"
    jwt_findings = [
        f for f in result["findings"] if f["kind"] == "secret" and f["severity"] == "MEDIUM"
    ]
    assert jwt_findings  # recorded on the side, but not blocking


def test_unreadable_changed_file_noted_and_passes(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    result = self_verify(["calc.py", "deleted_or_missing.py"], tmp_path)
    assert result["status"] == "passed"
    assert "不可读或已删除" in result["note"]


# -- Java contract checker layer ---------------------------------------------


def test_java_contract_regression_fails(tmp_path: Path) -> None:
    (tmp_path / "AccountController.java").write_text(JAVA_HEAD, encoding="utf-8")
    result = self_verify(
        ["AccountController.java"],
        tmp_path,
        base_files={"AccountController.java": JAVA_BASE},
    )
    assert result["status"] == "failed"
    contract_findings = [f for f in result["findings"] if f["kind"] == "contract"]
    assert contract_findings
    assert contract_findings[0]["pattern"] == "AUTH-01"
    assert contract_findings[0]["severity"] == "MAJOR"
    assert contract_findings[0]["file"] == "AccountController.java"


def test_java_clean_diff_passes(tmp_path: Path) -> None:
    (tmp_path / "AccountController.java").write_text(JAVA_BASE, encoding="utf-8")
    result = self_verify(
        ["AccountController.java"],
        tmp_path,
        base_files={"AccountController.java": JAVA_BASE},
    )
    assert result["status"] == "passed"
    assert result["findings"] == []
    assert "契约检查已运行" in result["note"]


def test_java_files_without_base_snapshot_skipped(tmp_path: Path) -> None:
    (tmp_path / "AccountController.java").write_text(JAVA_HEAD, encoding="utf-8")
    result = self_verify(["AccountController.java"], tmp_path)
    assert result["status"] == "skipped"
    assert "无 Base 快照" in result["note"]


def test_java_checker_unavailable_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "AccountController.java").write_text(JAVA_HEAD, encoding="utf-8")
    monkeypatch.setitem(sys.modules, "agent.checkers", None)
    result = self_verify(["AccountController.java"], tmp_path)
    assert result["status"] == "skipped"
    assert "契约检查器不可用" in result["note"]


def test_java_mocked_checker_finding_becomes_gate_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "AccountController.java").write_text(JAVA_HEAD, encoding="utf-8")

    def fake_checker(
        base_files: dict[str, str], head_files: dict[str, str],
    ) -> list[dict[str, Any]]:
        return [
            {
                "contract_id": "AUTH-01",
                "severity": "MAJOR",
                "type": "annotation_removed",
                "description": "mock checker hit",
                "location": "AccountController.java",
            }
        ]

    monkeypatch.setattr(agent.checkers, "run_contract_checks", fake_checker)
    result = self_verify(
        ["AccountController.java"],
        tmp_path,
        base_files={"AccountController.java": JAVA_BASE},
    )
    assert result["status"] == "failed"
    contract_findings = [f for f in result["findings"] if f["kind"] == "contract"]
    assert len(contract_findings) == 1
    assert contract_findings[0]["pattern"] == "AUTH-01"
    assert contract_findings[0]["description"] == "mock checker hit"


def test_java_checker_raises_skipped_with_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "AccountController.java").write_text(JAVA_HEAD, encoding="utf-8")

    def boom(base_files: dict[str, str], head_files: dict[str, str]) -> list[dict[str, Any]]:
        raise RuntimeError("checker boom")

    monkeypatch.setattr(agent.checkers, "run_contract_checks", boom)
    result = self_verify(
        ["AccountController.java"],
        tmp_path,
        base_files={"AccountController.java": JAVA_BASE},
    )
    assert result["status"] == "skipped"
    assert "抛错" in result["note"]
    assert "checker boom" in result["note"]


# -- scanner failure lanes (never faked, never a crash) ------------------------


def test_security_scanner_unavailable_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "calc.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "agent.security_scanner", None)
    result = self_verify(["calc.py"], tmp_path)
    assert result["status"] == "skipped"
    assert "安全扫描不可用" in result["note"]


def test_security_scanner_raises_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "calc.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    def boom(root: str) -> Any:
        raise RuntimeError("scanner boom")

    monkeypatch.setattr(agent.security_scanner, "scan_directory", boom)
    result = self_verify(["calc.py"], tmp_path)
    assert result["status"] == "skipped"
    assert "执行失败" in result["note"]
    assert "scanner boom" in result["note"]


# -- loop integration -----------------------------------------------------------


def test_loop_skip_self_verify_flag_marks_skipped(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    _loop, report = run_loop(tmp_path, {"test": fix_double}, skip_self_verify=True)
    assert report["result"] == "DONE"
    assert report["self_verify"]["status"] == "skipped"
    assert "--no-self-verify" in report["self_verify"]["note"]


def test_loop_self_verify_failure_overrides_done_to_failed(tmp_path: Path) -> None:
    write_fixture_repo(
        tmp_path,
        calc_body=(
            FAKE_KEY_LINE + "\n\n"
            "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
            '    return "hello " + name\n'
        ),
    )
    _loop, report = run_loop(tmp_path, {"test": fix_double})
    assert report["result"] == "FAILED"  # DONE overridden by the gate
    assert report["self_verify"]["status"] == "failed"
    assert "覆盖为 FAILED" in report["self_verify"]["note"]
    assert any(
        f["kind"] == "secret" and f["file"] == "calc.py"
        for f in report["self_verify"]["findings"]
    )
    # The fix is NOT rolled back: the edit stays, the report says so.
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


# -- CLI lane ---------------------------------------------------------------------


def test_cli_run_default_self_verify_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("SPECPROOF_SANDBOX", "local")
    write_fixture_repo(tmp_path)
    (tmp_path / "task.spec").write_text(FIX_SPEC, encoding="utf-8")
    fix_mod = write_fix_module(tmp_path, "fixes_ok.py")
    result = CliRunner().invoke(
        craft_cmd,
        [
            "run",
            "task.spec",
            "--repo",
            str(tmp_path),
            "--fix-module",
            str(fix_mod),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "self_verify.status=passed" in result.output
    job_dir = next((tmp_path / ".specraft" / "jobs").iterdir())
    report = json.loads((job_dir / "report.json").read_text(encoding="utf-8"))
    assert report["self_verify"]["status"] == "passed"
    assert report["self_verify"]["status"] != "not_implemented"


def test_cli_run_no_self_verify_skips_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("SPECPROOF_SANDBOX", "local")
    write_fixture_repo(tmp_path)
    (tmp_path / "task.spec").write_text(FIX_SPEC, encoding="utf-8")
    fix_mod = write_fix_module(tmp_path, "fixes_skip.py")
    result = CliRunner().invoke(
        craft_cmd,
        [
            "run",
            "task.spec",
            "--repo",
            str(tmp_path),
            "--fix-module",
            str(fix_mod),
            "--no-self-verify",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "自校验已跳过" in result.output
    job_dir = next((tmp_path / ".specraft" / "jobs").iterdir())
    report = json.loads((job_dir / "report.json").read_text(encoding="utf-8"))
    assert report["self_verify"]["status"] == "skipped"
    assert "--no-self-verify" in report["self_verify"]["note"]
