"""Layered acceptance-gate composition (W34 task 7).

GatePipeline composes five layered gates over a ChangeBundle before the
SpecProof accept hand-off (计划书 §4.6):

  Gate 1 run_test      — executor/test adapter; skipped with an honest note
                         when no test suite is detected (never faked as passed);
  Gate 2 run_build     — executor build adapter (per-ecosystem default command);
  Gate 3 run_typecheck — executor typecheck adapter (per-ecosystem);
  Gate 4 security      — agent.security_scanner secret patterns filtered to
                         the changed files + the SPECPROOF_CANARY_ sentinel
                         check (craft.verify.CANARY_MARKER);
  Gate 5 self_verify   — craft.verify.self_verify on the changed files, reused
                         verbatim (its behavior is unchanged).

Result contract: every gate adapter returns a GateResult carrying
{gate, status: passed|failed|skipped|error, note, findings, duration_ms}.
Composition (mirrors the repo's FAIL > PASS > UNVERIFIED convention):
FAIL beats SKIPPED beats PASS; error is the worst of all — one gate error
makes the overall verdict "error" with an honest note. A gate that cannot
run reports skipped/error with a note, never passed. No fake passes.

Testability: every exec gate takes an injected ExecRunner (default: the
sandbox Executor honoring SPECPROOF_SANDBOX), the security gate takes an
injected scan callable and the self-verify gate takes an injected verify
callable — the whole pipeline runs under fakes without network, LLM or
Docker.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from .executor import ExecResult, Executor
from .schemas import ChangeBundle
from .verify import CANARY_MARKER, self_verify

GateStatus = Literal["passed", "failed", "skipped", "error"]

GATE_ORDER: tuple[str, ...] = (
    "run_test",
    "run_build",
    "run_typecheck",
    "security",
    "self_verify",
)

# FAIL(2) > SKIPPED(1) > PASS(0); "error" is handled separately as the
# worst of all (it can never be outranked by a deterministic gate result).
GATE_RANK: dict[str, int] = {"passed": 0, "skipped": 1, "failed": 2}

_SKIPPED_DIR_PARTS = frozenset({".git", "__pycache__", "node_modules", ".venv", "venv", "target"})
_TEST_GLOBS = (
    "test_*.py",
    "*_test.py",
    "**/src/test/**/*.java",
    "*Test.java",
    "*Tests.java",
    "*IT.java",
)

SecurityScanFn = Callable[[str], Any]
SelfVerifyFn = Callable[..., dict[str, Any]]


class ExecRunner(Protocol):
    """Anything that executes one whitelisted command and returns ExecResult."""

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult: ...


@dataclass(frozen=True)
class GateResult:
    """One gate's honest outcome — the shared result contract."""

    gate: str
    status: GateStatus
    note: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status,
            "note": self.note,
            "findings": [dict(finding) for finding in self.findings],
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class GateReport:
    """Aggregated gate run: per-gate entries + overall verdict + summary."""

    task_id: str
    entries: tuple[GateResult, ...]
    overall: GateStatus
    overall_note: str
    duration_ms: int

    @property
    def summary_line(self) -> str:
        """Machine-greppable single line: 'GATES: task=... overall=... <gate=status>...'."""
        per_gate = " ".join(f"{entry.gate}={entry.status}" for entry in self.entries)
        return (
            f"GATES: task={self.task_id} overall={self.overall} {per_gate} "
            f"duration_ms={self.duration_ms}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "overall": self.overall,
            "overall_note": self.overall_note,
            "duration_ms": self.duration_ms,
            "gates": [entry.to_dict() for entry in self.entries],
            "summary": self.summary_line,
        }


def compose_verdict(entries: Iterable[GateResult]) -> tuple[GateStatus, str]:
    """FAIL > SKIPPED > PASS; any error is the worst of all, honestly noted."""
    ordered = list(entries)
    if not ordered:
        return "error", "未运行任何门禁, 无法认证 (不伪造通过)"
    if any(entry.status == "error" for entry in ordered):
        names = ", ".join(entry.gate for entry in ordered if entry.status == "error")
        return "error", f"门禁执行异常: {names} (error 为最差, 不伪造通过)"
    worst = max(
        (entry.status for entry in ordered), key=lambda status: GATE_RANK.get(status, -1)
    )
    if worst == "passed":
        return "passed", f"全部 {len(ordered)} 道门禁通过"
    if worst == "failed":
        names = ", ".join(entry.gate for entry in ordered if entry.status == "failed")
        return "failed", f"存在失败门禁 (FAIL > SKIPPED > PASS): {names}"
    names = ", ".join(entry.gate for entry in ordered if entry.status == "skipped")
    return "skipped", f"无失败但有跳过门禁 (SKIPPED > PASS, 不认证为通过): {names}"


def detect_test_suite(workspace: Path) -> list[str]:
    """Test files that prove a suite exists — evidence only, nothing runs."""
    found: list[str] = []
    for pattern in _TEST_GLOBS:
        for target in workspace.glob(f"**/{pattern}"):
            if not target.is_file():
                continue
            if any(part in _SKIPPED_DIR_PARTS for part in target.parts):
                continue
            rel = target.relative_to(workspace).as_posix()
            if rel not in found:
                found.append(rel)
    return found


def _resolve_executor(workspace: Path, executor: ExecRunner | None) -> ExecRunner:
    if executor is not None:
        return executor
    return Executor(workspace, mode=os.getenv("SPECPROOF_SANDBOX") or None)


def _run_commands(gate: str, commands: list[list[str]], executor: ExecRunner) -> GateResult:
    started = time.perf_counter()
    notes: list[str] = []
    findings: list[dict[str, Any]] = []
    errored = False
    for command in commands:
        label = " ".join(command)
        try:
            result = executor.run(command)
        except Exception as exc:
            errored = True
            notes.append(f"{label}: 执行异常 ({type(exc).__name__}: {exc})")
            continue
        if result.error:
            notes.append(f"{label}: sandbox 记录 error={result.error[:200]!r}")
        if result.exit_code == 0:
            notes.append(f"{label}: 通过 (exit 0, mode={result.mode})")
            continue
        findings.append(
            {
                "file": "",
                "line": None,
                "kind": gate,
                "severity": "HIGH",
                "pattern": "command_exit_nonzero",
                "description": f"{label}: exit {result.exit_code} — {result.output_tail[-600:]}",
            }
        )
        notes.append(f"{label}: 失败 (exit {result.exit_code}, mode={result.mode})")
    duration_ms = round((time.perf_counter() - started) * 1000)
    if errored:
        return GateResult(
            gate,
            "error",
            "; ".join(notes) or "命令执行异常, 无输出 (不伪造结果)",
            findings,
            duration_ms,

        )
    if findings:
        return GateResult(gate, "failed", "; ".join(notes), findings, duration_ms)
    return GateResult(gate, "passed", "; ".join(notes), [], duration_ms)


def run_test_gate(workspace: Path, *, executor: ExecRunner | None = None) -> GateResult:
    """Gate 1: run the detected test suite; skip honestly when none exists."""
    suite = detect_test_suite(workspace)
    if not suite:
        return GateResult(
            "run_test",
            "skipped",
            "未检测到测试文件 (test_*.py / *_test.py / *Test.java / src/test 等), "
            "run_test 无对象, 按 skipped 处理 (不伪造通过)",
            [],
            0,
        )
    notes: list[str] = [f"检测到 {len(suite)} 个测试文件"]
    commands: list[list[str]] = []
    if any(rel.endswith(".py") for rel in suite):
        commands.append(["python", "-m", "pytest", "-q"])
    java_tests = [rel for rel in suite if rel.endswith(".java")]
    if java_tests:
        if (workspace / "pom.xml").is_file():
            commands.append(["mvn", "-q", "test"])
        else:
            notes.append(
                f"检测到 {len(java_tests)} 个 Java 测试文件但仓库无 pom.xml, "
                "mvn test 无法运行, 该部分不执行 (诚实标注)"
            )
    if not commands:
        return GateResult(
            "run_test", "skipped", "; ".join(notes) + "; 无可用测试命令, 不伪造通过", [], 0
        )
    sub = _run_commands("run_test", commands, _resolve_executor(workspace, executor))
    return GateResult(
        "run_test",
        sub.status,
        "; ".join(notes) + "; " + sub.note,
        sub.findings,
        sub.duration_ms,
    )


def run_build_gate(workspace: Path, *, executor: ExecRunner | None = None) -> GateResult:
    """Gate 2: build via the detected ecosystem's default command."""
    runner = _resolve_executor(workspace, executor)
    if (workspace / "pom.xml").is_file():
        return _run_commands("run_build", [["mvn", "-q", "-DskipTests", "compile"]], runner)
    if (workspace / "build.gradle").is_file():
        return _run_commands("run_build", [["gradle", "-q", "compileJava"]], runner)
    if (workspace / "pyproject.toml").is_file() or (workspace / "setup.py").is_file():
        sub = _run_commands(
            "run_build", [["python", "-m", "compileall", "-q", "."]], runner
        )
        note = sub.note + "; python 以 compileall 字节码编译作为构建门 (无独立 build 阶段)"
        return GateResult("run_build", sub.status, note, sub.findings, sub.duration_ms)
    return GateResult(
        "run_build",
        "skipped",
        "未检测到构建配置 (pom.xml / build.gradle / pyproject.toml / setup.py), "
        "run_build 无对象, 按 skipped 处理 (不伪造通过)",
        [],
        0,
    )


def run_typecheck_gate(
    changed_files: Iterable[str],
    workspace: Path,
    *,
    executor: ExecRunner | None = None,
) -> GateResult:
    """Gate 3: typecheck the changed Python files; Java has no separate lane."""
    changed_py = sorted({str(rel) for rel in changed_files if str(rel).endswith(".py")})
    if changed_py:
        return _run_commands(
            "run_typecheck",
            [["python", "-m", "mypy", *changed_py]],
            _resolve_executor(workspace, executor),
        )
    if (workspace / "pom.xml").is_file() or (workspace / "build.gradle").is_file():
        return GateResult(
            "run_typecheck",
            "skipped",
            "Java 项目无独立 typecheck 命令 (由 build + Java 契约检查覆盖), "
            "改动亦无 .py 文件, 按 skipped 处理 (不伪造通过)",
            [],
            0,
        )
    return GateResult(
        "run_typecheck",
        "skipped",
        "改动无 .py 文件且未检测到类型检查配置, run_typecheck 无对象, "
        "按 skipped 处理 (不伪造通过)",
        [],
        0,
    )


def _read_workspace_file(workspace: Path, rel_path: str) -> str | None:
    target = workspace / rel_path
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def security_gate(
    changed_files: Iterable[str],
    workspace: Path,
    *,
    scan: SecurityScanFn | None = None,
) -> GateResult:
    """Gate 4: secret-pattern scan (agent.security_scanner) + canary sentinel.

    Only changed files block; MEDIUM/LOW findings are recorded on the side
    without blocking (mirrors craft.verify's CRITICAL/HIGH blocking rule).
    """
    changed = sorted({str(rel) for rel in changed_files})
    if not changed:
        return GateResult(
            "security", "skipped", "无改动文件, 安全扫描无对象, 按 skipped 处理 (不伪造通过)", [], 0
        )
    started = time.perf_counter()
    findings: list[dict[str, Any]] = []
    notes: list[str] = []
    try:
        if scan is not None:
            scan_result = scan(str(workspace))
        else:
            from agent.security_scanner import scan_directory

            scan_result = scan_directory(str(workspace))
    except Exception as exc:
        return GateResult(
            "security",
            "skipped",
            f"安全扫描不可用或执行失败 ({type(exc).__name__}: {exc}), 不伪造通过",
            [],
            round((time.perf_counter() - started) * 1000),
        )
    changed_set = set(changed)
    blocking = 0
    for entry in scan_result.findings:
        path = str(entry.path)
        if path not in changed_set:
            continue
        finding = {
            "file": path,
            "line": int(entry.line),
            "kind": "secret",
            "severity": str(entry.severity),
            "pattern": str(entry.pattern_name),
            "description": f"{entry.pattern_name} (命中已脱敏: {entry.matched_text})",
        }
        findings.append(finding)
        if finding["severity"] in ("CRITICAL", "HIGH"):
            blocking += 1
    for rel in changed:
        content = _read_workspace_file(workspace, rel)
        if content is None:
            notes.append(f"{rel}: 不可读或已删除, 跳过 canary 检查")
            continue
        if CANARY_MARKER in content:
            line = next(
                (
                    number
                    for number, text in enumerate(content.splitlines(), 1)
                    if CANARY_MARKER in text
                ),
                1,
            )
            findings.append(
                {
                    "file": rel,
                    "line": line,
                    "kind": "canary",
                    "severity": "CRITICAL",
                    "pattern": "Canary secret",
                    "description": (
                        "canary 哨兵字符串出现在改动文件 (SPECPROOF_CANARY_...), 禁止交付"
                    ),
                }
            )
            blocking += 1
    duration_ms = round((time.perf_counter() - started) * 1000)
    if blocking:
        notes.append(
            f"安全门失败: {blocking} 项硬门 finding (CRITICAL/HIGH 密钥或 canary), 交付被拦截"
        )
        return GateResult("security", "failed", "; ".join(notes), findings, duration_ms)
    if findings:
        notes.append(f"{len(findings)} 项非阻塞 finding (MEDIUM/LOW) 记录在案, 不阻塞")
        return GateResult("security", "passed", "; ".join(notes), findings, duration_ms)
    notes.append(f"改动文件 {len(changed)} 个无密钥/canary finding")
    return GateResult("security", "passed", "; ".join(notes), [], duration_ms)


def self_verify_gate(
    changed_files: Iterable[str],
    workspace: Path,
    *,
    base_files: Mapping[str, str] | None = None,
    verify_fn: SelfVerifyFn | None = None,
) -> GateResult:
    """Gate 5: SpecProof M3 self-verify (craft.verify.self_verify) reused verbatim."""
    changed = sorted({str(rel) for rel in changed_files})
    started = time.perf_counter()
    try:
        if verify_fn is not None:
            raw = verify_fn(changed, workspace, base_files=dict(base_files or {}))
        else:
            raw = self_verify(changed, workspace, base_files=dict(base_files or {}))
    except Exception as exc:
        return GateResult(
            "self_verify",
            "error",
            f"self_verify 执行异常 ({type(exc).__name__}: {exc}), 不伪造通过",
            [],
            round((time.perf_counter() - started) * 1000),
        )
    if not isinstance(raw, dict):
        return GateResult(
            "self_verify",
            "error",
            f"self_verify 返回非法类型 {type(raw).__name__} (期望 dict), 不伪造通过",
            [],
            round((time.perf_counter() - started) * 1000),
        )
    raw_status = raw.get("status")
    if raw_status not in ("passed", "failed", "skipped"):
        return GateResult(
            "self_verify",
            "error",
            f"self_verify 返回未知 status {raw_status!r}, 不伪造通过",
            [],
            round((time.perf_counter() - started) * 1000),
        )
    raw_findings = raw.get("findings") or []
    findings = [dict(item) for item in raw_findings if isinstance(item, dict)]
    note = str(raw.get("note") or "")
    return GateResult(
        "self_verify",
        cast(GateStatus, raw_status),
        note,
        findings,
        round((time.perf_counter() - started) * 1000),
    )


@dataclass
class GatePipeline:
    """Composes the layered gates for a ChangeBundle and produces a GateReport."""

    workspace: Path
    executor: ExecRunner | None = None
    security_scan: SecurityScanFn | None = None
    self_verify_fn: SelfVerifyFn | None = None
    enabled_gates: tuple[str, ...] = GATE_ORDER

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace)
        unknown = sorted(set(self.enabled_gates) - set(GATE_ORDER))
        if unknown:
            raise ValueError(f"未注册的门禁: {unknown} (可用: {list(GATE_ORDER)})")

    def run(
        self,
        bundle: ChangeBundle,
        *,
        base_files: Mapping[str, str] | None = None,
        changed_files: Iterable[str] | None = None,
    ) -> GateReport:
        """Run every enabled gate in order; a gate exception becomes an error entry."""
        changed = sorted(
            {
                str(rel)
                for rel in (bundle.changed_files if changed_files is None else changed_files)
            }
        )
        started = time.perf_counter()
        entries: list[GateResult] = []
        for name in self.enabled_gates:
            try:
                entries.append(self._run_gate(name, changed, base_files))
            except Exception as exc:
                entries.append(
                    GateResult(
                        name,
                        "error",
                        f"门禁 {name} 执行异常 ({type(exc).__name__}: {exc}), 不伪造结果",
                        [],
                        0,
                    )
                )
        duration_ms = round((time.perf_counter() - started) * 1000)
        overall, note = compose_verdict(entries)
        return GateReport(
            task_id=bundle.task_id,
            entries=tuple(entries),
            overall=overall,
            overall_note=note,
            duration_ms=duration_ms,
        )

    def _run_gate(
        self, name: str, changed: list[str], base_files: Mapping[str, str] | None
    ) -> GateResult:
        if name == "run_test":
            return run_test_gate(self.workspace, executor=self.executor)
        if name == "run_build":
            return run_build_gate(self.workspace, executor=self.executor)
        if name == "run_typecheck":
            return run_typecheck_gate(changed, self.workspace, executor=self.executor)
        if name == "security":
            return security_gate(changed, self.workspace, scan=self.security_scan)
        if name == "self_verify":
            return self_verify_gate(
                changed, self.workspace, base_files=base_files, verify_fn=self.self_verify_fn
            )
        raise ValueError(f"未注册的门禁: {name!r}")


__all__ = [
    "GATE_ORDER",
    "GatePipeline",
    "GateReport",
    "GateResult",
    "GateStatus",
    "compose_verdict",
    "detect_test_suite",
    "run_build_gate",
    "run_test_gate",
    "run_typecheck_gate",
    "security_gate",
    "self_verify_gate",
]
