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
import sys
from dataclasses import dataclass, field
from pathlib import Path

import defusedxml.ElementTree as SafeET

from sandbox.runner import (
    ISOLATION_PLANES,
    MAVEN_PROFILE,
    NODE_PROFILE,
    PYTHON_PROFILE,
    SANDBOX_MODE_ENV,
    SandboxProfile,
    SandboxResult,
    deployment_plane_pin,
    run_sandboxed,
)

ALLOWED_COMMANDS: frozenset[str] = frozenset({"mvn", "gradle", "npm", "pytest", "python", "cargo"})
OUTPUT_TAIL_CHARS = 4000
STACK_LINE_LIMIT = 5
DEFAULT_TIMEOUT = 600

#: Which container toolchain a whitelisted command stem needs. Before this
#: table craft commands reached ``run_sandboxed`` with no ``profile=``, whose
#: default is Maven-only, so a plane pinned to docker executed ``pytest`` /
#: ``npm test`` inside the java image and failed for the wrong reason.
PROFILE_BY_STEM: dict[str, SandboxProfile] = {
    "mvn": MAVEN_PROFILE,
    "npm": NODE_PROFILE,
    "pytest": PYTHON_PROFILE,
    "python": PYTHON_PROFILE,
}

class PlaneToolchainMissingError(RuntimeError):
    """The pinned container plane has no toolchain image for this command."""


def stems_without_profile() -> set[str]:
    """Whitelisted stems that have no container image — derived, never typed."""
    return set(ALLOWED_COMMANDS) - set(PROFILE_BY_STEM)


def craft_plane_decision() -> tuple[str, str]:
    """Return ``(plane, note)`` for the craft repair loop's command execution.

    ``Executor`` now picks a container profile per command stem, so a pinned
    docker plane runs each language in its own image. That is still not enough
    to move THIS path onto the pinned plane, and the note says why instead of
    letting it read as covered: the repair loop's commands are the model's
    choice, and every whitelisted stem in ``stems_without_profile()`` (today
    ``gradle``/``cargo`` — no image exists) would be refused on a pinned plane.
    A craft job could then die on a step the sandbox cannot serve at all, so
    craft stays on the host plane ON PURPOSE and the disclosure rides the job
    log, keeping THREAT_TESTING.md §1's "缓解事实" honest about this path.
    """
    pinned = deployment_plane_pin()
    if not pinned or pinned == "local":
        return "local", ""
    outcome = (
        "会被拒绝而不是被隔离"
        if pinned in ISOLATION_PLANES
        else f"会经 {pinned} 面落到宿主执行而不是被隔离"
    )
    return "local", (
        f"部署钉了 {SANDBOX_MODE_ENV}={pinned}，但 craft 修复回路仍在 local 面 ——"
        " 该沙箱缓解对这条路径未生效: Executor 已按命令词干选 profile，"
        f"而白名单里 {sorted(stems_without_profile())} 没有任何镜像，"
        f"钉住这个面时这些命令{outcome}"
    )


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
    # The sandbox's own cache-integrity statement (#7/#141). A cache-mounting
    # profile always fills it in — an empty string means "this profile mounts
    # no cache", never "the cache was verified".
    cache_note: str = ""

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
    """Whitelisted command execution via the sandbox runner.

    python (optional): an absolute interpreter path used in place of the
    bare "python"/"pytest" command stems — e.g. a per-run venv interpreter
    in the SWE-bench LLM harness. Local mode defaults to the running interpreter
    so subprocesses share
    the installed dependencies; container mode keeps container PATH resolution.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        mode: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        python: str | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.mode = mode
        self.timeout = timeout
        effective_mode = mode or deployment_plane_pin() or "auto"
        self.effective_mode = effective_mode
        self.python = python or (sys.executable if effective_mode == "local" else None)

    def allowed_commands(self) -> set[str]:
        extra = os.getenv("CRAFT_EXTRA_COMMANDS", "")
        return set(ALLOWED_COMMANDS) | {t.strip().lower() for t in extra.split(",") if t.strip()}

    def _resolve_command(self, command: list[str]) -> list[str]:
        """Substitute the configured interpreter for the bare python/pytest
        stems; every other command passes through untouched."""
        if self.python and command and command[0] in ("python", "pytest"):
            if command[0] == "pytest":
                return [self.python, "-m", "pytest", *command[1:]]
            return [self.python, *command[1:]]
        return command

    def _requested_stem(self, argv0: str) -> str:
        """The stem the whitelist judges.

        ``run_pytest`` and ``_resolve_command`` put OUR configured interpreter
        into argv[0]; that path must count as ``python`` instead of becoming a
        command nobody asked for. A caller-supplied path is still judged by its
        own stem, so this widens nothing: asking for the interpreter was already
        legal as the bare name.
        """
        if self.python and argv0 == self.python:
            return "python"
        return Path(argv0).stem.lower()

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult:
        if not command:
            raise CommandNotAllowedError("命令为空")
        # The whitelist judges the command that was ASKED FOR. Resolution may
        # substitute our own configured interpreter into argv[0], and that
        # substitution must never be able to make a legal command illegal: a
        # host whose interpreter is python3.12 used to refuse "pytest" here.
        stem = self._requested_stem(command[0])
        if stem not in self.allowed_commands():
            raise CommandNotAllowedError(
                f"命令 '{command[0]}' 不在白名单 {sorted(self.allowed_commands())} "
                "(M1 默认拒绝其余命令)"
            )
        resolved = self._resolve_command(command)
        profile = PROFILE_BY_STEM.get(stem)
        if profile is None and self.effective_mode in ISOLATION_PLANES:
            raise PlaneToolchainMissingError(
                f"命令词干 {stem!r} 没有容器镜像，而执行面钉了 {self.effective_mode}"
                f" —— 既不塞进 {MAVEN_PROFILE.name} 镜像跑错工具链，也不落到宿主；"
                f"缺镜像的词干: {sorted(stems_without_profile())}"
            )
        result: SandboxResult = run_sandboxed(
            command=resolved,
            workspace=str(self.workspace),
            timeout=timeout if timeout is not None else self.timeout,
            mode=self.mode,
            profile=profile,
        )
        combined = f"{result.stdout}\n{result.stderr}".rstrip()
        if not combined and result.error:
            # Sandbox-level failures (spawn errors, timeouts) must never
            # surface as silent empty output: the real error rides the tail.
            combined = f"[sandbox error] {result.error}".rstrip()
        return ExecResult(
            command=list(resolved),
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            output_tail=combined[-OUTPUT_TAIL_CHARS:],
            truncated=len(combined) > OUTPUT_TAIL_CHARS,
            error=result.error,
            mode=result.mode,
            cache_note=result.cache_note,
        )

    def run_pytest(self, extra_args: list[str] | None = None) -> ExecResult:
        return self.run([self.python or "python", "-m", "pytest", "-q", *(extra_args or [])])

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
