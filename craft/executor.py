"""M1 executor (design doc §4.4): whitelisted commands through
sandbox.run_sandboxed, with honest truncation and JUnit/surefire parsing.

- command whitelist: mvn / gradle / npm / pytest / python / cargo (default
  deny for everything else; CRAFT_EXTRA_COMMANDS appends comma-separated
  names for experiments);
- every command runs through sandbox.run_sandboxed; the returned mode
  (docker | local_fallback | local) is recorded verbatim on the result;
- timeout and output truncation: the combined output keeps its tail 4000
  chars and the truncated flag is set truthfully;
- surefire XML reports are parsed with defusedxml (workspace content is
  untrusted); when no XML exists the report is honestly empty plus a note.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import defusedxml.ElementTree as SafeET

from sandbox.runner import SandboxResult, run_sandboxed

ALLOWED_COMMANDS: frozenset[str] = frozenset({"mvn", "gradle", "npm", "pytest", "python", "cargo"})
OUTPUT_TAIL_CHARS = 4000
STACK_LINE_LIMIT = 5
DEFAULT_TIMEOUT = 600


class CommandNotAllowedError(RuntimeError):
    """A command outside the M1 whitelist was requested."""


@dataclass(frozen=True)
class ExecResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    output_tail: str
    truncated: bool
    error: str
    mode: str

    @property
    def combined(self) -> str:
        return f"{self.stdout}\n{self.stderr}".rstrip()


@dataclass(frozen=True)
class FailedTest:
    name: str
    classname: str
    message: str
    stack_lines: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "classname": self.classname,
            "message": self.message,
            "stack_lines": list(self.stack_lines),
        }


@dataclass(frozen=True)
class TestReport:
    reports_found: int
    failed_tests: list[FailedTest] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "reports_found": self.reports_found,
            "failed_tests": [test.to_dict() for test in self.failed_tests],
            "note": self.note,
        }


_PYTEST_FAILED_RE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.MULTILINE)


def extract_pytest_failed_tests(output: str) -> list[str]:
    """Failed test node ids from pytest -q output (FAILED <nodeid> lines)."""
    return [match.group(1) for match in _PYTEST_FAILED_RE.finditer(output)]


class Executor:
    """Whitelisted command execution via the sandbox runner."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        mode: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.workspace = Path(workspace)
        self.mode = mode
        self.timeout = timeout

    def allowed_commands(self) -> set[str]:
        extra = os.getenv("CRAFT_EXTRA_COMMANDS", "")
        return set(ALLOWED_COMMANDS) | {t.strip().lower() for t in extra.split(",") if t.strip()}

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult:
        if not command:
            raise CommandNotAllowedError("命令为空")
        stem = Path(command[0]).stem.lower()
        if stem not in self.allowed_commands():
            raise CommandNotAllowedError(
                f"命令 '{command[0]}' 不在白名单 {sorted(self.allowed_commands())} "
                "(M1 默认拒绝其余命令)"
            )
        result: SandboxResult = run_sandboxed(
            command=command,
            workspace=str(self.workspace),
            timeout=timeout if timeout is not None else self.timeout,
            mode=self.mode,
        )
        combined = f"{result.stdout}\n{result.stderr}".rstrip()
        return ExecResult(
            command=list(command),
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            output_tail=combined[-OUTPUT_TAIL_CHARS:],
            truncated=len(combined) > OUTPUT_TAIL_CHARS,
            error=result.error,
            mode=result.mode,
        )

    def run_pytest(self, extra_args: list[str] | None = None) -> ExecResult:
        return self.run(["python", "-m", "pytest", "-q", *(extra_args or [])])

    def parse_test_results(self) -> TestReport:
        """Parse surefire/JUnit XML with defusedxml; honest empty + note when
        no reports exist (then exit code and output remain the evidence)."""
        pattern = "**/target/surefire-reports/*.xml"
        reports = sorted(self.workspace.glob(pattern))
        if not reports:
            return TestReport(
                reports_found=0,
                note="未找到 surefire XML 报告 (target/surefire-reports/*.xml): "
                "以命令退出码与输出为准",
            )
        failed: list[FailedTest] = []
        parse_errors: list[str] = []
        for report in reports:
            try:
                root = SafeET.parse(str(report)).getroot()
            except (OSError, SafeET.ParseError) as exc:
                parse_errors.append(f"{report.name}: 解析失败 ({exc})")
                continue
            for case in root.iter("testcase"):
                problem = case.find("failure")
                if problem is None:
                    problem = case.find("error")
                if problem is None:
                    continue
                message = problem.get("message") or ""
                text = (problem.text or "").strip()
                stack_lines = [
                    line for line in text.splitlines()[:STACK_LINE_LIMIT] if line.strip()
                ]
                if not message and stack_lines:
                    message = stack_lines[0]
                failed.append(
                    FailedTest(
                        name=case.get("name") or "",
                        classname=case.get("classname") or "",
                        message=message[:500],
                        stack_lines=stack_lines,
                    )
                )
        note = f"解析 {len(reports)} 个 surefire 报告, {len(failed)} 个失败用例"
        if parse_errors:
            note += "; " + "; ".join(parse_errors)
        return TestReport(reports_found=len(reports), failed_tests=failed, note=note)
