"""Execution adapter protocol + compatibility matrix (guide §4.5, task 10 — Q lane).

The sandbox (sandbox/runner.py) executes UNTRUSTED PR code in Docker
(non-root, --network none, read-only workspace, seeded Maven cache volume).
This module is the plugin seam on top of it: every language/build-tool
combination is an ExecutionAdapter that declares what it can execute and
under which offline policy, instead of the pipeline hardcoding "mvnw".

Guide §4.5 contract:

    class ExecutionAdapter(Protocol):
        def detect(self, repo: RepositorySnapshot) -> RuntimeProfile: ...
        def prepare(self, request: ExecutionRequest) -> PreparedExecution: ...
        def run(self, prepared: PreparedExecution) -> ExecutionResult: ...
        def collect(self, prepared: PreparedExecution) -> EvidenceFragment: ...
        def cleanup(self, prepared: PreparedExecution) -> None: ...

First adapter batch (guide §14 task 10): Java/Maven is IMPLEMENTED (the
existing capability, re-homed behind the protocol); Python/pytest is
IMPLEMENTED local-first (工业化指南 阶段 4 / W57 — a project .venv on the
host, no container). Java/Gradle, Node and Go remain planned matrix rows
whose detect functions raise AdapterNotImplemented — we do NOT claim to
support arbitrary projects.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sandbox.runner import (
    DEFAULT_M2_VOLUME,
    DEFAULT_PIDS_LIMIT,
    SANDBOX_USER,
    run_sandboxed,
)

# ── Domain dataclasses ──────────────────────────────────────────────────


@dataclass(frozen=True)
class RepositorySnapshot:
    """Minimal repository view for adapter detection (never full clones)."""

    path: str
    # Optional pre-collected relative file list (tests/other detectors can
    # pass it instead of touching disk); empty means "inspect the filesystem".
    files: tuple[str, ...] = ()

    def has(self, relative: str) -> bool:
        rel = relative.replace("\\", "/").lstrip("./")
        if rel in self.files:
            return True
        try:
            return (Path(self.path) / relative).exists()
        except OSError:
            return False


@dataclass(frozen=True)
class RuntimeProfile:
    """What a detector knows about a repository's execution runtime."""

    language: str
    build_tool: str
    test_runner: str
    known_limits: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionRequest:
    """One execution the pipeline asks an adapter to prepare.

    goal is "test_compile" or "run_test" (the two Maven goals the
    differential pipeline needs today); other goals are adapter-specific.
    """

    workspace: str
    goal: str
    test_class: str = ""
    skip_main: bool = False
    timeout: int = 600
    sandbox_mode: str | None = None  # None = sandbox env policy (auto)


@dataclass
class PreparedExecution:
    """Everything needed to run one prepared execution.

    command is the sandbox-internal command (container /work layout);
    local_command is the documented local fallback (explicit SPECPROOF_SANDBOX
    mode=local or transient sandbox failure under mode=auto). result is
    attached by run() so collect() can report exit evidence without a
    second, stateful channel.
    """

    workdir: str
    command: list[str]
    local_command: list[str]
    image: str
    image_digest: str
    offline_policy: str
    timeout: int
    sandbox_mode: str | None = None
    result: ExecutionResult | None = None


@dataclass(frozen=True)
class ExecutionResult:
    """Run outcome. stdout_tail/stderr_tail are the capped output tails
    (guide §4.5 output-length limit) — the surefire summary sits at the end
    of Maven output, so the tail keeps every parseable evidence line.
    """

    exit_code: int
    stdout_tail: str
    stderr_tail: str
    mode: str
    sandbox_resources: dict[str, str] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class EvidenceFragment:
    """Evidence the adapter can point at after a run (guide §4.7 lineage)."""

    test_report_refs: tuple[str, ...]
    exit_evidence: dict[str, Any]


@dataclass(frozen=True)
class MatrixRow:
    """One compatibility-matrix row (docs/architecture/EXECUTION_COMPATIBILITY.md)."""

    language: str
    build_tool: str
    test_runner: str
    status: str
    image: str
    image_digest: str
    toolchain: str
    offline_policy: str
    known_limits: tuple[str, ...]


# ── Protocol ────────────────────────────────────────────────────────────


class AdapterNotImplemented(Exception):  # noqa: N818 — name fixed by guide §4.5/task vocabulary
    """Raised when a repository has no implemented adapter (fail-closed).

    Planned matrix rows raise this from detect(); the registry falls through
    to the next adapter and fails the whole lookup when nothing matches.
    """


@runtime_checkable
class ExecutionAdapter(Protocol):
    def detect(self, repo: RepositorySnapshot) -> RuntimeProfile: ...

    def prepare(self, request: ExecutionRequest) -> PreparedExecution: ...

    def run(self, prepared: PreparedExecution) -> ExecutionResult: ...

    def collect(self, prepared: PreparedExecution) -> EvidenceFragment: ...

    def cleanup(self, prepared: PreparedExecution) -> None: ...


# ── Output handling ─────────────────────────────────────────────────────

# Capped output tail per execution (guide §4.5 output-length limit). Maven's
# surefire summary ("Tests run: ...") and any "COMPILATION ERROR" marker
# appear at the END of the output, so the tail keeps them parseable while
# bounding memory for adversarial build plugins.
OUTPUT_TAIL_CHARS = 256_000

_SURFIRE_SUMMARY = re.compile(
    r"Tests run:\s*(\d+).*?Failures:\s*(\d+).*?Errors:\s*(\d+).*?Skipped:\s*(\d+)",
    re.DOTALL,
)


def parse_surefire_summary(text: str) -> dict[str, int]:
    """Parse the surefire "Tests run:" summary line out of Maven output."""
    m = _SURFIRE_SUMMARY.search(text)
    if m:
        return {
            "tests": int(m.group(1)),
            "failures": int(m.group(2)),
            "errors": int(m.group(3)),
            "skipped": int(m.group(4)),
        }
    return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}


def _tail(text: str, limit: int = OUTPUT_TAIL_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


_PYTEST_PASSED = re.compile(r"(\d+)\s+passed")
_PYTEST_FAILED = re.compile(r"(\d+)\s+failed")
_PYTEST_SKIPPED = re.compile(r"(\d+)\s+skipped")


def parse_pytest_summary(text: str) -> dict[str, int]:
    """Parse the pytest short summary ("N passed[, M failed][, K skipped]")
    out of `pytest -q` output. Absent counters parse to 0 (no evidence);
    pytest folds errors into "failed", so errors is always 0 here."""
    def _count(pattern: re.Pattern[str]) -> int:
        match = pattern.search(text)
        return int(match.group(1)) if match else 0

    passed = _count(_PYTEST_PASSED)
    failed = _count(_PYTEST_FAILED)
    return {
        "tests": passed + failed,
        "passed": passed,
        "failed": failed,
        "skipped": _count(_PYTEST_SKIPPED),
        "errors": 0,
    }


def _maven_wrapper(workspace: str) -> str:
    """Maven wrapper script path for the local fallback (CreateProcessW on
    Windows resolves relative names against the parent cwd, so the path must
    be absolute — same rule the pre-adapter pipeline already followed)."""
    script = "mvnw.cmd" if platform.system() == "Windows" else "mvnw"
    return os.path.join(workspace, script)


# ── Execution-time probe artifacts (fault-injection roadmap, 阶段4) ─────
#
# The demo's test-scoped probe scaffolding (injected into the case refs by
# scripts/build_golden_scenarios.py) writes a machine-readable JSON artifact
# after each probe test method:
#
#   {
#     "probe_version": 1,
#     "publish_count": 1,
#     "outcome": "success" | "error",
#     "payloads": [ { "exchange", "routingKey", "type",
#                     "timestamp": str | null, "failed": bool } ]
#   }
#
# The differential node reads one artifact per ref and compares them against
# the case's probe_expectation (ground-truth.json). Invalid or absent
# artifacts parse to None — an invalid artifact is "no evidence", never
# fabricated evidence.

PROBE_ARTIFACT_REL = "target/specproof-probe.json"

_PROBE_PAYLOAD_KEYS = ("exchange", "routingKey", "type", "timestamp", "failed")


def parse_probe_artifact(text: str) -> dict[str, Any] | None:
    """Parse + schema-validate a probe artifact. None on any violation."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("probe_version"), int):
        return None
    if not isinstance(data.get("publish_count"), int):
        return None
    payloads = data.get("payloads")
    if not isinstance(payloads, list):
        return None
    if len(payloads) != data["publish_count"]:
        return None
    for payload in payloads:
        if not isinstance(payload, dict):
            return None
        if not all(key in payload for key in _PROBE_PAYLOAD_KEYS):
            return None
        if payload.get("timestamp") is not None and not isinstance(
            payload["timestamp"], str
        ):
            return None
        if not isinstance(payload.get("failed"), bool):
            return None
    return data


# ── Java/Maven adapter (implemented) ────────────────────────────────────


class JavaMavenAdapter:
    """Java/Maven via the execution sandbox (guide §4.5 first adapter).

    Declarations (verified on this machine, 2026-08-18 — see the
    compatibility matrix doc):
      image          maven:3.9-eclipse-temurin-21
      digest         sha256:c07f7ccf... (docker image inspect, this host)
      toolchain      Maven 3.9.9 (wrapper 3.3.2) / Eclipse Temurin JDK 21
      offline policy mvn -o inside --network none; every artifact resolves
                     from the seeded volume specproof-maven-cache-1000
                     (docs/operations/RUNBOOK.md §5, seed_sandbox_cache.ps1).
    """

    IMAGE = "maven:3.9-eclipse-temurin-21"
    IMAGE_DIGEST = (
        "sha256:c07f7ccfb8ca6c9fa29ee523f00afa7d2ca6132c92f8652c4aebb5ee3491f502"
    )
    TOOLCHAIN = "Maven 3.9.9 (wrapper 3.3.2) / Eclipse Temurin JDK 21"
    OFFLINE_POLICY = (
        "mvn -o inside --network none; artifacts resolve exclusively from the "
        "seeded cache volume specproof-maven-cache-1000 "
        "(docs/operations/RUNBOOK.md §5, scripts/seed_sandbox_cache.ps1); "
        "local fallback uses the repo Maven wrapper against the host ~/.m2"
    )
    KNOWN_LIMITS: tuple[str, ...] = (
        "离线依赖需预置缓存卷, 否则 fail-closed 失败 (RUNBOOK §5)",
        "local 回退需要宿主 JDK 21 + Maven wrapper",
        "确定性测试模板只支持 demo 仓库 (com.specproof.demo)",
        "输出按尾部 256000 字符截断 (§4.5 输出长度限制)",
        "镜像 digest 为 2026-08-18 本机验证值, 预拉/seed 时须复核",
    )

    def detect(self, repo: RepositorySnapshot) -> RuntimeProfile:
        if repo.has("pom.xml") and repo.has("src/main/java"):
            return RuntimeProfile(
                language="java",
                build_tool="maven",
                test_runner="junit5 + maven-surefire",
                known_limits=self.KNOWN_LIMITS,
            )
        raise AdapterNotImplemented(
            "Java/Maven detect rule (pom.xml + src/main/java) does not match"
        )

    # ── Probe hooks (fault-injection roadmap, 阶段4) ──
    # The probe test is a normal surefire run through prepare()/run() with
    # test_class "SpecProofProbeTest#<method>"; these hooks expose the
    # artifact the probe test left behind.

    def probe_test_class(self, method: str = "") -> str:
        """Surefire selector for the probe test (whole class or one method)."""
        if method:
            return "SpecProofProbeTest#" + method
        return "SpecProofProbeTest"

    def read_probe_artifact(self, workspace: str) -> dict[str, Any] | None:
        """Read + validate target/specproof-probe.json from a workspace.

        Returns the parsed artifact, or None when the file is absent or
        invalid (an invalid artifact is "no evidence", never fabricated
        evidence).
        """
        artifact = Path(workspace) / PROBE_ARTIFACT_REL
        try:
            text = artifact.read_text(encoding="utf-8")
        except OSError:
            return None
        return parse_probe_artifact(text)

    def prepare(self, request: ExecutionRequest) -> PreparedExecution:
        workspace = request.workspace
        wrapper = _maven_wrapper(workspace)
        if request.goal == "test_compile":
            command = ["mvn", "-o", "test-compile", "-q", "-f", "/work/pom.xml"]
            local_command = [wrapper, "test-compile", "-q"]
        elif request.goal == "run_test":
            command = [
                "mvn", "-o", "test", "-q",
                f"-Dtest={request.test_class}",
                "-DfailIfNoTests=false",
                "-f", "/work/pom.xml",
            ] + (["-Dmaven.main.skip=true"] if request.skip_main else [])
            local_command = [
                wrapper, "test", "-q",
                f"-Dtest={request.test_class}",
                "-DfailIfNoTests=false",
            ] + (["-Dmaven.main.skip=true"] if request.skip_main else [])
        else:
            raise AdapterNotImplemented(f"unsupported Maven goal: {request.goal}")
        return PreparedExecution(
            workdir=workspace,
            command=command,
            local_command=local_command,
            image=self.IMAGE,
            image_digest=self.IMAGE_DIGEST,
            offline_policy=self.OFFLINE_POLICY,
            timeout=request.timeout,
            sandbox_mode=request.sandbox_mode,
        )

    def run(self, prepared: PreparedExecution) -> ExecutionResult:
        sandbox_result = run_sandboxed(
            prepared.command,
            workspace=prepared.workdir,
            timeout=prepared.timeout,
            mode=prepared.sandbox_mode,
            local_command=prepared.local_command,
        )
        prepared.result = ExecutionResult(
            exit_code=sandbox_result.exit_code,
            stdout_tail=_tail(sandbox_result.stdout),
            stderr_tail=_tail(sandbox_result.stderr),
            mode=sandbox_result.mode,
            sandbox_resources={
                # What the sandbox runner enforces for this adapter's runs
                # (sandbox/runner.py constants; §12 hardening).
                "user": SANDBOX_USER,
                "network": "none",
                "capabilities": "drop ALL",
                "no_new_privileges": "true",
                "pids_limit": os.getenv("SPECPROOF_SANDBOX_PIDS", DEFAULT_PIDS_LIMIT),
                "m2_volume": (
                    os.getenv("SPECPROOF_SANDBOX_M2_VOLUME", "").strip()
                    or DEFAULT_M2_VOLUME
                ),
                "workspace_mount": "ro (target/ writable sub-mount)",
            },
            error=sandbox_result.error,
        )
        return prepared.result

    def collect(self, prepared: PreparedExecution) -> EvidenceFragment:
        reports_dir = Path(prepared.workdir) / "target" / "surefire-reports"
        refs = (
            str(reports_dir / "TEST-com.specproof.demo.SpecProofGeneratedTest.xml"),
            str(reports_dir / "TEST-com.specproof.demo.SpecProofGeneratedTest.txt"),
        )
        result = prepared.result
        if result is None:
            return EvidenceFragment(
                test_report_refs=refs,
                exit_evidence={"exit_code": None, "collected": False},
            )
        combined = result.stdout_tail + result.stderr_tail
        return EvidenceFragment(
            test_report_refs=refs,
            exit_evidence={
                "exit_code": result.exit_code,
                "mode": result.mode,
                "sandbox_resources": dict(result.sandbox_resources),
                "test_counts": parse_surefire_summary(combined),
            },
        )

    def cleanup(self, prepared: PreparedExecution) -> None:
        """Worktree cleanup boundary (guide §4.5 "工作目录自动回收").

        Deliberately a no-op here: the disposable worktree is pipeline-owned
        (git worktree remove), sandbox containers run --rm so container
        state dies with them, and local-mode target/ is retained on purpose
        — the P6 build cache reuses compiled classes. Adapters must never
        delete the workspace or target/ themselves.
        """
        return None


# ── Python/pytest adapter (local-first, 工业化指南 阶段 4 / W57) ─────


@dataclass(frozen=True)
class LocalRunResult:
    """One host-side subprocess run (Python adapter local-first execution).

    error is non-empty only when the process could not be run to completion
    (launch failure or timeout); exit_code is -1 in those cases.
    """

    exit_code: int
    stdout: str
    stderr: str
    error: str = ""


def _run_local(command: list[str], cwd: str, timeout: int) -> LocalRunResult:
    """Run a command on the host without a shell; never raise on child
    failure — failures surface as exit_code/error so the adapter can
    classify them honestly (venv_create / pip_install / run timeout)."""
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return LocalRunResult(
            exit_code=-1,
            stdout="",
            stderr="",
            error=f"command timed out after {timeout}s: {' '.join(command)[:200]}",
        )
    except OSError as exc:
        return LocalRunResult(exit_code=-1, stdout="", stderr="", error=str(exc))
    return LocalRunResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _venv_python(venv_dir: Path) -> Path:
    """Interpreter path inside a venv (Scripts/python.exe on Windows)."""
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


class PythonEnvironmentError(Exception):
    """Honest environment failure while provisioning a Python project.

    stage classifies the failing step: "venv_create" or "pip_install".
    Callers must surface this error — it is never retried silently and
    never faked as a successful setup.
    """

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"python environment {stage} failed: {message}")


class PythonAdapter:
    """Python/pytest via a project-local virtualenv (local-first adapter).

    Declarations (host-executed; no container):
      image          —  (local-first: pytest runs against the host)
      toolchain      CPython <host version> / `python -m venv` + pip / pytest
      offline policy reuse the project .venv when present; otherwise create
                      it with `python -m venv` (offline-safe) and
                      pip-install requirements.txt — the install itself may
                      need network on first provision, and a pip failure is
                      reported honestly as PythonEnvironmentError.
    """

    VENV_DIR = ".venv"
    ENV_SETUP_TIMEOUT = 600
    TOOLCHAIN = f"CPython {platform.python_version()} (host) / venv + pip / pytest"
    OFFLINE_POLICY = (
        "local-first: reuse the project .venv when present; otherwise "
        "`python -m venv .venv` (offline-safe) + `pip install -r "
        "requirements.txt` — first-time dependency install may require "
        "network and fails honestly (PythonEnvironmentError) on pip errors"
    )
    KNOWN_LIMITS: tuple[str, ...] = (
        "local-first 执行 (无容器沙箱): 宿主 CPython + 项目 .venv",
        "首次 pip install -r requirements.txt 可能需要网络; 失败如实报错 "
        "(PythonEnvironmentError, stage=venv_create/pip_install)",
        "复用已存在的 .venv 时跳过依赖安装 (信任既有环境)",
        "仅支持 pytest (goal=run_test); 其他 goal 抛 AdapterNotImplemented",
        "detect 规则: pyproject.toml | requirements.txt | pytest.ini; "
        "exotic Python 项目抛 AdapterNotImplemented",
        "输出按尾部 256000 字符截断 (§4.5 输出长度限制)",
        "SPECPROOF_KEEP_VENV 设置时 cleanup 保留 .venv, 否则移除",
    )

    def detect(self, repo: RepositorySnapshot) -> RuntimeProfile:
        if (
            repo.has("pyproject.toml")
            or repo.has("requirements.txt")
            or repo.has("pytest.ini")
        ):
            return RuntimeProfile(
                language="python",
                build_tool="pip",
                test_runner="pytest",
                known_limits=self.KNOWN_LIMITS,
            )
        raise AdapterNotImplemented(
            "Python detect rule (pyproject.toml | requirements.txt | "
            "pytest.ini) does not match"
        )

    def prepare(self, request: ExecutionRequest) -> PreparedExecution:
        if request.goal != "run_test":
            raise AdapterNotImplemented(
                f"unsupported Python goal: {request.goal} "
                "(PythonAdapter supports run_test only)"
            )
        workspace = Path(request.workspace)
        venv_dir = workspace / self.VENV_DIR
        python = _venv_python(venv_dir)
        if not python.is_file():
            self._create_venv(venv_dir)
            requirements = workspace / "requirements.txt"
            if requirements.is_file():
                self._pip_install(python, requirements)
        command = [str(python), "-m", "pytest", "-q"]
        if request.test_class:
            command += ["-k", request.test_class]
        return PreparedExecution(
            workdir=str(workspace),
            command=command,
            local_command=list(command),
            image="—",
            image_digest="—",
            offline_policy=self.OFFLINE_POLICY,
            timeout=request.timeout,
            sandbox_mode=request.sandbox_mode,
        )

    def _create_venv(self, venv_dir: Path) -> None:
        result = _run_local(
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=str(venv_dir.parent),
            timeout=self.ENV_SETUP_TIMEOUT,
        )
        if result.exit_code != 0:
            raise PythonEnvironmentError(
                "venv_create",
                f"python -m venv exited {result.exit_code}: "
                + _tail(result.stderr, 2000),
            )

    def _pip_install(self, python: Path, requirements: Path) -> None:
        result = _run_local(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(requirements),
            ],
            cwd=str(requirements.parent),
            timeout=self.ENV_SETUP_TIMEOUT,
        )
        if result.exit_code != 0:
            raise PythonEnvironmentError(
                "pip_install",
                f"pip install -r {requirements.name} exited {result.exit_code}: "
                + _tail(result.stdout + result.stderr, 2000),
            )

    def run(self, prepared: PreparedExecution) -> ExecutionResult:
        result = _run_local(
            prepared.command,
            cwd=prepared.workdir,
            timeout=prepared.timeout,
        )
        prepared.result = ExecutionResult(
            exit_code=result.exit_code,
            stdout_tail=_tail(result.stdout),
            stderr_tail=_tail(result.stderr),
            mode="local",
            sandbox_resources={
                "sandbox": "none (local-first execution on the host)",
                "network": "host (first-time pip install may require it)",
                "workspace": "read-write (project .venv lives inside)",
            },
            error=result.error,
        )
        return prepared.result

    def collect(self, prepared: PreparedExecution) -> EvidenceFragment:
        result = prepared.result
        if result is None:
            return EvidenceFragment(
                test_report_refs=(),
                exit_evidence={"exit_code": None, "collected": False},
            )
        combined = result.stdout_tail + result.stderr_tail
        return EvidenceFragment(
            test_report_refs=(),
            exit_evidence={
                "exit_code": result.exit_code,
                "mode": result.mode,
                "sandbox_resources": dict(result.sandbox_resources),
                "test_counts": parse_pytest_summary(combined),
            },
        )

    def cleanup(self, prepared: PreparedExecution) -> None:
        """venv cleanup boundary (local-first mirror of guide §4.5 cleanup).

        Removes the project .venv unless SPECPROOF_KEEP_VENV is set (any
        non-empty value). Windows interpreter locks are tolerated via
        rmtree(ignore_errors=True) — a leftover directory is a workspace
        disposal concern, never fabricated success. The workspace itself
        and every other file in it are pipeline-owned and never touched.
        """
        if os.getenv("SPECPROOF_KEEP_VENV", "").strip():
            return None
        venv_dir = Path(prepared.workdir) / self.VENV_DIR
        if venv_dir.is_dir():
            shutil.rmtree(venv_dir, ignore_errors=True)
        return None


# ── Planned adapters (matrix only; detect raises, per guide §14 task 10) ──


def detect_java_gradle(repo: RepositorySnapshot) -> RuntimeProfile:
    raise AdapterNotImplemented(
        "Java/Gradle adapter is planned (compatibility matrix status=planned); "
        "no executor is wired"
    )


def detect_node(repo: RepositorySnapshot) -> RuntimeProfile:
    raise AdapterNotImplemented(
        "Node adapter is planned (compatibility matrix status=planned); "
        "no executor is wired"
    )


def detect_go(repo: RepositorySnapshot) -> RuntimeProfile:
    raise AdapterNotImplemented(
        "Go adapter is planned (compatibility matrix status=planned); "
        "no executor is wired"
    )


class _PlannedAdapter:
    """Matrix placeholder: every protocol method fails closed with
    AdapterNotImplemented — the detect functions exist so callers (and the
    registry) can see WHICH planned row a repository would need."""

    def __init__(
        self,
        name: str,
        detect_fn: Callable[[RepositorySnapshot], RuntimeProfile],
    ) -> None:
        self._name = name
        self._detect_fn = detect_fn

    def detect(self, repo: RepositorySnapshot) -> RuntimeProfile:
        return self._detect_fn(repo)

    def prepare(self, request: ExecutionRequest) -> PreparedExecution:
        raise AdapterNotImplemented(
            f"{self._name} adapter is planned (compatibility matrix status=planned)"
        )

    def run(self, prepared: PreparedExecution) -> ExecutionResult:
        raise AdapterNotImplemented(
            f"{self._name} adapter is planned (compatibility matrix status=planned)"
        )

    def collect(self, prepared: PreparedExecution) -> EvidenceFragment:
        raise AdapterNotImplemented(
            f"{self._name} adapter is planned (compatibility matrix status=planned)"
        )

    def cleanup(self, prepared: PreparedExecution) -> None:
        raise AdapterNotImplemented(
            f"{self._name} adapter is planned (compatibility matrix status=planned)"
        )


# ── Compatibility matrix (single source of truth for the doc + tests) ────

COMPATIBILITY_MATRIX: tuple[MatrixRow, ...] = (
    MatrixRow(
        language="Java",
        build_tool="Maven",
        test_runner="JUnit 5 + Surefire",
        status="已支持 (实测)",
        image=JavaMavenAdapter.IMAGE,
        image_digest=JavaMavenAdapter.IMAGE_DIGEST,
        toolchain=JavaMavenAdapter.TOOLCHAIN,
        offline_policy=JavaMavenAdapter.OFFLINE_POLICY,
        known_limits=JavaMavenAdapter.KNOWN_LIMITS,
    ),
    MatrixRow(
        language="Java",
        build_tool="Gradle",
        test_runner="JUnit 5 (Gradle Test)",
        status="规划 (planned)",
        image="—",
        image_digest="—",
        toolchain="待定 (随实现声明)",
        offline_policy="待定 (离线缓存策略随实现声明)",
        known_limits=("detect 抛 AdapterNotImplemented; 无执行器",),
    ),
    MatrixRow(
        language="JavaScript/TypeScript",
        build_tool="npm",
        test_runner="Jest",
        status="规划 (planned)",
        image="—",
        image_digest="—",
        toolchain="待定 (随实现声明)",
        offline_policy="待定 (离线缓存策略随实现声明)",
        known_limits=("detect 抛 AdapterNotImplemented; 无执行器",),
    ),
    MatrixRow(
        language="Python",
        build_tool="pip",
        test_runner="pytest",
        status="已支持 (local-first)",
        image="—",
        image_digest="—",
        toolchain=PythonAdapter.TOOLCHAIN,
        offline_policy=PythonAdapter.OFFLINE_POLICY,
        known_limits=PythonAdapter.KNOWN_LIMITS,
    ),
    MatrixRow(
        language="Go",
        build_tool="go build",
        test_runner="go test",
        status="规划 (planned)",
        image="—",
        image_digest="—",
        toolchain="待定 (随实现声明)",
        offline_policy="待定 (离线缓存策略随实现声明)",
        known_limits=("detect 抛 AdapterNotImplemented; 无执行器",),
    ),
)


# ── Registry ─────────────────────────────────────────────────────────────


class ExecutionAdapterRegistry:
    """Adapters are consulted in registration order (Java/Maven first)."""

    def __init__(self) -> None:
        self._adapters: list[ExecutionAdapter] = [
            JavaMavenAdapter(),
            _PlannedAdapter("Java/Gradle", detect_java_gradle),
            _PlannedAdapter("Node", detect_node),
            PythonAdapter(),
            _PlannedAdapter("Go", detect_go),
        ]

    @property
    def adapters(self) -> tuple[ExecutionAdapter, ...]:
        return tuple(self._adapters)

    def get(self, repo: RepositorySnapshot) -> ExecutionAdapter:
        """First adapter whose detect() accepts the repository; otherwise
        AdapterNotImplemented (fail-closed — never execute an unclaimed repo)."""
        failures: list[str] = []
        for adapter in self._adapters:
            try:
                adapter.detect(repo)
                return adapter
            except AdapterNotImplemented as exc:
                failures.append(str(exc))
        raise AdapterNotImplemented(
            "unsupported repository — no execution adapter matched: "
            + "; ".join(failures)
        )

    def profile(self, repo: RepositorySnapshot) -> RuntimeProfile:
        return self.get(repo).detect(repo)

    def matrix(self) -> tuple[MatrixRow, ...]:
        return COMPATIBILITY_MATRIX


registry = ExecutionAdapterRegistry()
