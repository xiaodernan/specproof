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

import json
import os
import re
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from sandbox.runner import deployment_plane_pin

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

#: Test-file patterns grouped by the kind of suite they prove. ``_TEST_GLOBS`` and
#: the 「未检测到测试文件」 inventory are BOTH derived from this table, so a pattern
#: can never be recognised by the detector while staying unnamed in the refusal (or
#: the other way round — #366 measured exactly that pair for gradle/go).
#: ``run_test_gate`` walks the buckets this table produces, and a kind that
#: reaches the dispatch without a branch raises instead of answering: #426
#: measured that a hand-copied roster of subscripts leaks ``KeyError`` when the
#: table loses a row and — worse — reports 「检测到 2 个测试文件」 with ``passed``
#: when the table gains one nothing runs.
_TEST_GLOBS_BY_KIND: dict[str, tuple[str, ...]] = {
    "python": ("test_*.py", "*_test.py"),
    "java": ("**/src/test/**/*.java", "*Test.java", "*Tests.java", "*IT.java"),
    "go": ("*_test.go",),
    "node": (
        "*.test.js",
        "*.test.jsx",
        "*.test.ts",
        "*.test.tsx",
        "*.spec.js",
        "*.spec.jsx",
        "*.spec.ts",
        "*.spec.tsx",
    ),
}
_TEST_GLOBS: tuple[str, ...] = tuple(
    pattern for globs in _TEST_GLOBS_BY_KIND.values() for pattern in globs
)


@dataclass(frozen=True)
class _BuildRoute:
    """One ecosystem the build gate can serve, and the markers that name it.

    ``markers`` is the only place the 「未检测到构建配置」 inventory comes from, and
    the dispatch below has to answer for every ``kind`` listed here. ``language``
    groups the two Java ecosystems: the Java test command and the 「Java 项目无独立
    typecheck 命令」 branch both read that declaration instead of naming maven and
    gradle a second time by hand, which #426 measured raising ``KeyError`` out of a
    function declared ``-> GateResult`` as soon as a route row is dropped.
    """

    kind: str
    markers: tuple[str, ...]
    language: str
    test_command: tuple[str, ...] = ()
    note_extra: str = ""


#: Dispatch order. The kinds craft already served keep their precedence, so
#: adding go/node cannot silently re-route a Maven or Python repository. The two
#: Java routes stay adjacent so ``mvn`` outranks ``gradle`` wherever both exist.
_BUILD_ROUTES: tuple[_BuildRoute, ...] = (
    _BuildRoute("maven", ("pom.xml",), "java", ("mvn", "-q", "test")),
    # The test_command lives on the route because run_test_gate picks mvn/gradle
    # off this table. #423 could only add the gradle answer after #366 routed the
    # gradle stem to GRADLE_PROFILE; before that craft refused the command for
    # want of a profile and 「test 均无法运行」 was the honest note.
    _BuildRoute("gradle", ("build.gradle", "build.gradle.kts"), "java", ("gradle", "-q", "test")),
    _BuildRoute(
        "python",
        ("pyproject.toml", "setup.py"),
        "python",
        note_extra="python 以 compileall 字节码编译作为构建门 (无独立 build 阶段)",
    ),
    _BuildRoute("go", ("go.mod",), "go"),
    _BuildRoute("node", ("package.json",), "node"),
)
#: #487 deleted the ``_BUILD_MARKERS`` copy that used to live here: it had no
#: production reader (the note reads ``_BUILD_MARKER_INVENTORY``, the dispatch
#: reads ``_BUILD_ROUTES``), and the one gate that read it compared it with its
#: own derivation. The build markers live in ``_BUILD_ROUTES`` and nowhere else.
_BUILD_MARKER_INVENTORY = " / ".join(marker for route in _BUILD_ROUTES for marker in route.markers)
_TEST_INVENTORY = " / ".join(_TEST_GLOBS)


@dataclass(frozen=True)
class _JavaServing:
    """What the build table currently says about Java.

    Read at call time on purpose: #426's legs change one route row and require the
    「均无法运行」 disclosure to follow, which a module-level copy could not show —
    it would only ever equal the derivation of the bytes that were imported.
    """

    routes: tuple[_BuildRoute, ...]
    markers: tuple[str, ...]
    stems: tuple[str, ...]


def _java_serving() -> _JavaServing:
    """Every route that serves Java, in dispatch order, with what it makes runnable."""
    routes = tuple(route for route in _BUILD_ROUTES if route.language == "java")
    return _JavaServing(
        routes=routes,
        markers=tuple(marker for route in routes for marker in route.markers),
        stems=tuple(route.test_command[0] for route in routes if route.test_command),
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


def _compile_test_glob(pattern: str) -> re.Pattern[str]:
    """Compile one detector pattern into a matcher over a relative POSIX path.

    The `**/` prefix the old detector passed to ``Path.glob`` means "zero or more
    directories", so a relative path is enough to reproduce its verdict — which is
    what lets the walk below prune instead of judging after the fact.
    """
    chunks = f"**/{pattern}".split("/")
    parts: list[str] = []
    for index, chunk in enumerate(chunks):
        if chunk == "**":
            parts.append("(?:[^/]+/)*")
        elif index == len(chunks) - 1:
            parts.append("".join("[^/]*" if c == "*" else re.escape(c) for c in chunk))
        else:
            parts.append("".join("[^/]*" if c == "*" else re.escape(c) for c in chunk) + "/")
    return re.compile("^" + "".join(parts) + "$")


def _compile_matchers(
    table: Mapping[str, tuple[str, ...]]
) -> dict[str, tuple[re.Pattern[str], ...]]:
    """The matcher set of a vocabulary table — one reading, also what tests call.

    A leg that swaps a row in ``_TEST_GLOBS_BY_KIND`` has to rebuild the matchers
    the same way the module did; going through this function keeps that a call to
    the producer instead of a second copy of its comprehension.
    """
    return {
        kind: tuple(_compile_test_glob(pattern) for pattern in patterns)
        for kind, patterns in table.items()
    }


_TEST_MATCHERS: dict[str, tuple[re.Pattern[str], ...]] = _compile_matchers(_TEST_GLOBS_BY_KIND)


def _is_ignored_directory(directory: Path) -> bool:
    """A directory the detector never descends into.

    The name list covers ``.venv``/``venv``/``target``/``__pycache__``, but #423
    counted 183 test-named files under this repository's ``.venv312`` — a
    virtualenv is not named ``venv``, it is a directory that holds ``pyvenv.cfg``.
    """
    return directory.name in _SKIPPED_DIR_PARTS or (directory / "pyvenv.cfg").is_file()


def _walk_source_files(workspace: Path) -> Iterator[str]:
    """Every file under the workspace as a relative POSIX path, skip dirs pruned.

    The detector used to ask ``workspace.glob("/**/<pattern>")`` once per pattern
    and filter afterwards. #423 measured that on ``apps/web``: 15 patterns walked
    52 raw hits in 38.40 s and kept 47 of them, while the single pruned walk
    returned the identical 47 in 0.80 s. The walk cost was never bounded by the
    ignore list, and widening the table from 6 patterns to 15 multiplied it.
    """
    for dirpath, dirnames, filenames in os.walk(workspace):
        base = Path(dirpath)
        dirnames[:] = [name for name in dirnames if not _is_ignored_directory(base / name)]
        for name in filenames:
            yield (base / name).relative_to(workspace).as_posix()


def _detect_suite_by_kind(workspace: Path) -> dict[str, list[str]]:
    """Test files grouped by the kind whose command they are evidence for."""
    found: dict[str, list[str]] = {kind: [] for kind in _TEST_MATCHERS}
    for rel in _walk_source_files(workspace):
        # a file whose own name is a skip word stays excluded, as under the glob
        if any(part in _SKIPPED_DIR_PARTS for part in rel.split("/")):
            continue
        for kind, matchers in _TEST_MATCHERS.items():
            if any(matcher.match(rel) for matcher in matchers):
                found[kind].append(rel)
    return found


def detect_test_suite(workspace: Path) -> list[str]:
    """Test files that prove a suite exists — evidence only, nothing runs."""
    ordered: list[str] = []
    for bucket in _detect_suite_by_kind(workspace).values():
        ordered.extend(rel for rel in bucket if rel not in ordered)
    return ordered


def _resolve_executor(workspace: Path, executor: ExecRunner | None) -> ExecRunner:
    if executor is not None:
        return executor
    return Executor(workspace, mode=deployment_plane_pin() or None)


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
        # 缓存完整性 (backlog #7/#141): the sandbox's own statement belongs in
        # the same note the console already renders mode= from. Dropped here,
        # an honest "NOT VERIFIED" never reaches a reviewer. An empty note
        # means the profile mounted no cache — that must not be written as a
        # claim, so the suffix is absent, not "verified".
        cache_suffix = f", 缓存={result.cache_note}" if result.cache_note else ""
        if result.exit_code == 0:
            notes.append(f"{label}: 通过 (exit 0, mode={result.mode}{cache_suffix})")
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
        notes.append(f"{label}: 失败 (exit {result.exit_code}, mode={result.mode}{cache_suffix})")
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
    by_kind = _detect_suite_by_kind(workspace)
    suite = [rel for bucket in by_kind.values() for rel in bucket]
    if not suite:
        return GateResult(
            "run_test",
            "skipped",
            f"未检测到测试文件 ({_TEST_INVENTORY}), "
            "run_test 无对象, 按 skipped 处理 (不伪造通过)",
            [],
            0,
        )
    notes: list[str] = [f"检测到 {len(suite)} 个测试文件"]
    commands: list[list[str]] = []
    # Walking the detector's own buckets is what keeps the count above honest: a
    # kind is either answered below or refused, never silently counted.
    for kind, bucket in by_kind.items():
        if not bucket:
            continue
        if kind == "python":
            commands.append(["python", "-m", "pytest", "-q"])
        elif kind == "java":
            serving = _java_serving()
            present = next(
                (
                    route
                    for route in serving.routes
                    if any((workspace / marker).is_file() for marker in route.markers)
                ),
                None,
            )
            if present is None:
                notes.append(
                    f"检测到 {len(bucket)} 个 Java 测试文件但仓库无 "
                    f"{' / '.join(serving.markers)}, "
                    f"{'·'.join(serving.stems)} test 均无法运行, 该部分不执行 (诚实标注)"
                )
            elif not present.test_command:
                raise AssertionError(
                    f"run_test_gate found {present.kind}'s build file but the route declares "
                    f"no test_command — {len(bucket)} Java test files would be counted "
                    "and run by nothing"
                )
            else:
                commands.append(list(present.test_command))
        elif kind == "go":
            commands.append(["go", "test", "./..."])
        elif kind == "node":
            scripts = _package_scripts(workspace)
            if scripts is None:
                notes.append(
                    "package.json 读不出或不是 JSON 对象, npm test 无从判定, "
                    "该部分不执行 (诚实标注)"
                )
            elif not str(scripts.get("test", "")).strip():
                notes.append(
                    f"检测到 {len(bucket)} 个 JS/TS 测试文件但 package.json "
                    "无 scripts.test, npm test 无法运行, 该部分不执行 (诚实标注)"
                )
            else:
                commands.append(["npm", "test", "--silent"])
        else:
            raise AssertionError(
                f"run_test_gate's table names the kind {kind!r} but no branch dispatches it; "
                f"{len(bucket)} file(s) of that kind are counted in the note and run by nothing"
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


def _package_scripts(workspace: Path) -> dict[str, Any] | None:
    """The ``scripts`` map of package.json, or None when it cannot be read as one.

    Node has no universal test or build command: the repository's own manifest
    declares both. This is the same requirement ``agent/preflight.py`` names
    (「package.json has no 'scripts.test'」) and the same one
    ``experiments/adapters.py``'s Node detect rule checks.
    """
    raw = _read_workspace_file(workspace, "package.json")
    if raw is None:
        return None
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        return None
    scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
    return scripts if isinstance(scripts, dict) else None


def run_build_gate(workspace: Path, *, executor: ExecRunner | None = None) -> GateResult:
    """Gate 2: build via the detected ecosystem's default command."""
    runner = _resolve_executor(workspace, executor)
    for route in _BUILD_ROUTES:
        if not any((workspace / marker).is_file() for marker in route.markers):
            continue
        if route.kind == "maven":
            sub = _run_commands("run_build", [["mvn", "-q", "-DskipTests", "compile"]], runner)
        elif route.kind == "gradle":
            sub = _run_commands("run_build", [["gradle", "-q", "compileJava"]], runner)
        elif route.kind == "python":
            sub = _run_commands("run_build", [["python", "-m", "compileall", "-q", "."]], runner)
        elif route.kind == "go":
            sub = _run_commands("run_build", [["go", "build", "./..."]], runner)
        elif route.kind == "node":
            scripts = _package_scripts(workspace)
            if scripts is None or not str(scripts.get("build", "")).strip():
                return GateResult(
                    "run_build",
                    "skipped",
                    "package.json 存在但没读出 scripts.build, npm run build 无对象, "
                    "按 skipped 处理 (不伪造通过)",
                    [],
                    0,
                )
            sub = _run_commands("run_build", [["npm", "run", "build"]], runner)
        else:
            raise AssertionError(
                f"run_build_gate's table names the kind {route.kind!r} but no branch "
                "dispatches it — an unrouted kind would be built by nothing"
            )
        note = sub.note + (f"; {route.note_extra}" if route.note_extra else "")
        return GateResult("run_build", sub.status, note, sub.findings, sub.duration_ms)
    return GateResult(
        "run_build",
        "skipped",
        f"未检测到构建配置 ({_BUILD_MARKER_INVENTORY}), "
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
    """Gate 3: typecheck the changed Python files; Java has no separate lane.

    If the typechecker (mypy) is not installed in the environment, the gate
    reports skipped with an honest note — a missing tool must never be
    confused with a code problem and must never fail a delivery.
    """
    changed_py = sorted({str(rel) for rel in changed_files if str(rel).endswith(".py")})
    if changed_py:
        runner = _resolve_executor(workspace, executor)
        try:
            probe = runner.run(["python", "-m", "mypy", "--version"])
        except Exception as exc:  # noqa: BLE001 — tool probe failure ⇒ skipped
            return GateResult(
                "run_typecheck", "skipped",
                "mypy 不可用 (执行异常: " + str(exc) + "), 无类型检查器可运行, "
                "按 skipped 处理 (不伪造通过)",
                [], 0,
            )
        if probe.exit_code != 0:
            return GateResult(
                "run_typecheck", "skipped",
                "mypy 不可用 (退出码 " + str(probe.exit_code) + "), 无类型检查器可运行, "
                "按 skipped 处理 (不伪造通过)",
                [], 0,
            )
        return _run_commands(
            "run_typecheck",
            [["python", "-m", "mypy", *changed_py]],
            runner,
        )
    if any((workspace / marker).is_file() for marker in _java_serving().markers):
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
