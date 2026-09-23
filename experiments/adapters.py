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

Adapter status (kept in sync with the classes below):
  * Java/Maven — IMPLEMENTED (sandboxed Maven; the existing capability
    re-homed behind the protocol).
  * Python/pytest — IMPLEMENTED local-first (工业化指南 阶段 4 / W57 — a
    project .venv on the host, no container).
  * Node/npm — IMPLEMENTED in the Docker sandbox (runs the project's own
    ``npm test --silent`` with --network none and a read-only /work; Jest /
    Vitest / node:test summaries parsed, a missing ``node_modules`` fails
    honestly rather than faking a pass). Host execution is opt-in by name.
  * Java/Gradle and Go — NOT implemented; ``detect`` raises
    AdapterNotImplemented. We do NOT claim to support arbitrary projects.

Every adapter also declares ``EXECUTION_SURFACE`` (see the surface section
below): WHERE run() executes a repository's code. Callers must read it before
deciding whether running untrusted repo tests is allowed at all.
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
    DEFAULT_NODE_IMAGE,
    DEFAULT_PIDS_LIMIT,
    NODE_PROFILE,
    SANDBOX_USER,
    run_sandboxed,
)

# ── Declared execution surface ───────────────────────────────────────────
#
# WHERE an adapter's run() executes a repository's own code. This is a DECLARED
# class property, deliberately not inferred from the run result: the verify
# pipeline will not execute UNTRUSTED repo-authored tests on the host without
# an operator opting in, so the decision has to be readable BEFORE anything
# runs. Callers read it with getattr(..., SURFACE_HOST) so an adapter that
# forgets to declare is treated as the dangerous case, never the safe one.
SURFACE_DOCKER_SANDBOX = "docker_sandbox"
SURFACE_HOST = "host"


def execution_surface_of(adapter: Any) -> str:
    """Declared surface of an adapter, failing closed to host execution."""
    return getattr(adapter, "EXECUTION_SURFACE", SURFACE_HOST)


def runs_in_sandbox(adapter: Any) -> bool:
    """True only when this adapter executes repository code inside the
    hardened container. Callers decide safety with this, never by matching
    surface strings themselves."""
    return execution_surface_of(adapter) == SURFACE_DOCKER_SANDBOX


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


# ── Node test summary parsers (npm / jest / vitest / node:test) ──────────

_JEST_TOTAL = re.compile(
    r"Tests:\s+(?:.*?(\d+)\s+failed,\s+)?(\d+)\s+passed,\s+"
    r"(?:.*?(\d+)\s+skipped,\s+)?(\d+)\s+total"
)
_VITEST_SUMMARY = re.compile(
    r"Tests\s+(?:(\d+)\s+failed\s*\|\s*)?(?:(\d+)\s+skipped\s*\|\s*)?"
    r"(\d+)\s+passed(?:\s*\((\d+)\))?"
)
_NODE_TEST_TOTAL = re.compile(r"^# tests\s+(\d+)", re.MULTILINE)
_NODE_TEST_PASS = re.compile(r"^# pass\s+(\d+)", re.MULTILINE)
_NODE_TEST_FAIL = re.compile(r"^# fail\s+(\d+)", re.MULTILINE)
_NODE_TEST_SKIPPED = re.compile(r"^# skipped\s+(\d+)", re.MULTILINE)


def parse_node_test_summary(text: str) -> dict[str, int]:
    """Parse a Node test-suite summary into test counts.

    Supports the three common terminal reporters — Jest, Vitest and Node's
    built-in ``--test`` TAP output. When no recognised summary is present it
    returns all-zero counts (honest "no evidence"): a zero is never a pass,
    the caller must read exit_code for the verdict.
    """
    m = _JEST_TOTAL.search(text)
    if m:
        return {
            "tests": int(m.group(4)),
            "passed": int(m.group(2)),
            "failed": int(m.group(1) or 0),
            "errors": 0,
            "skipped": int(m.group(3) or 0),
        }
    m = _VITEST_SUMMARY.search(text)
    if m:
        failed = int(m.group(1) or 0)
        skipped = int(m.group(2) or 0)
        passed = int(m.group(3))
        total = int(m.group(4) or (passed + failed + skipped))
        return {
            "tests": total,
            "passed": passed,
            "failed": failed,
            "errors": 0,
            "skipped": skipped,
        }
    tests_m = _NODE_TEST_TOTAL.search(text)
    pass_m = _NODE_TEST_PASS.search(text)
    fail_m = _NODE_TEST_FAIL.search(text)
    if tests_m or pass_m or fail_m:
        failed = int(fail_m.group(1)) if fail_m else 0
        passed = int(pass_m.group(1)) if pass_m else 0
        skipped_m = _NODE_TEST_SKIPPED.search(text)
        skipped = int(skipped_m.group(1)) if skipped_m else 0
        total = int(tests_m.group(1)) if tests_m else (passed + failed + skipped)
        return {
            "tests": total,
            "passed": passed,
            "failed": failed,
            "errors": 0,
            "skipped": skipped,
        }
    return {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}


def _node_image() -> str:
    """Image a Node sandbox run actually uses, honoring the same operator
    override the runner applies when it builds the argv."""
    return os.getenv("SPECPROOF_SANDBOX_NODE_IMAGE", "").strip() or DEFAULT_NODE_IMAGE


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
    EXECUTION_SURFACE = SURFACE_DOCKER_SANDBOX
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
    EXECUTION_SURFACE = SURFACE_HOST
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


# ── Node/npm adapter (Docker sandbox) ────────────────────────────────────


class NodeAdapter:
    """JavaScript/TypeScript via the project's own ``npm test`` (Docker sandbox).

    Runs the repository's declared test script with ``npm test --silent`` inside
    the hardened container (non-root, --network none, read-only /work) and
    parses the terminal summary from Jest, Vitest or Node's built-in ``--test``
    runner. A repository's own test script is UNTRUSTED input, so the default
    is sandboxed and ``mode="docker"`` is passed explicitly: unlike ``auto`` it
    never degrades to running on the host. Host execution happens ONLY when a
    caller asks for it by name (``sandbox_mode="local"``).

    No dependency install is performed, so a missing ``node_modules`` surfaces
    honestly as a non-zero exit rather than a fabricated pass; under
    --network none an install could not happen anyway.
    """

    TOOLCHAIN = "Node/npm (docker sandbox) / npm test / jest | vitest | node:test"
    EXECUTION_SURFACE = SURFACE_DOCKER_SANDBOX
    IMAGE = DEFAULT_NODE_IMAGE
    #: Verified with `docker image inspect` on this host, 2026-09-23. Not the
    #: ref the runner pulls (that stays the tag, like the Maven row) — it is
    #: the fingerprint of the image this adapter was actually validated on.
    IMAGE_DIGEST = (
        "sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85"
    )
    OFFLINE_POLICY = (
        "docker sandbox with --network none: executes the project's own"
        " `npm test --silent`; no dependency install is attempted, so the"
        " workspace must already carry node_modules (otherwise npm exits"
        " non-zero and that is reported as-is, never as a pass)"
    )
    KNOWN_LIMITS: tuple[str, ...] = (
        "容器沙箱执行 (node:22-alpine, 非 root uid 1000, --network none)",
        "不安装依赖: workspace 需已备好 node_modules, 否则 npm test 非零退出 "
        "(如实上报, 不伪造通过); 而管线的 `git worktree` 检出不含未跟踪文件, 故"
        "当前真实覆盖面是零依赖的 node:test 项目, 需装依赖的仓库判 "
        "NON_REPRODUCIBLE 而非通过",
        "仅支持 goal=run_test; test_compile 无对应语义, 抛 AdapterNotImplemented",
        "汇总解析支持 Jest / Vitest / node:test; 无法识别时计数为 0 (无证据), "
        "判定以 exit_code 为准",
        "detect 规则: package.json 且声明了 test 脚本",
        "/work 全程只读 (无 writable 子挂载): 向源码树写文件的测试会失败",
        "镜像 digest 为 2026-09-23 本机验证值, 预拉/升级 node:22-alpine 时须复核",
        "输出按尾部 256000 字符截断 (§4.5 输出长度限制)",
    )

    def detect(self, repo: RepositorySnapshot) -> RuntimeProfile:
        pkg = Path(repo.path) / "package.json"
        if not pkg.is_file():
            raise AdapterNotImplemented(
                "Node detect rule (package.json with a test script) does not match"
            )
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if not (isinstance(scripts, dict) and scripts.get("test")):
            raise AdapterNotImplemented(
                "Node detect rule (package.json with a test script) does not "
                "match: no `scripts.test` command declared"
            )
        return RuntimeProfile(
            language="javascript/typescript",
            build_tool="npm",
            test_runner="jest | vitest | node:test",
            known_limits=self.KNOWN_LIMITS,
        )

    def prepare(self, request: ExecutionRequest) -> PreparedExecution:
        if request.goal != "run_test":
            raise AdapterNotImplemented(
                f"unsupported Node goal: {request.goal} "
                "(NodeAdapter supports run_test only)"
            )
        command = ["npm", "test", "--silent"]
        if request.test_class:
            # Forward a name filter to the underlying runner via npm passthrough.
            command += ["--", "-t", request.test_class]
        image = _node_image()
        return PreparedExecution(
            workdir=request.workspace,
            command=command,
            local_command=list(command),
            image=image,
            # Only the default image carries the digest this adapter was
            # validated on; an operator-supplied image is unidentified here.
            image_digest=self.IMAGE_DIGEST if image == self.IMAGE else "—",
            offline_policy=self.OFFLINE_POLICY,
            timeout=request.timeout,
            sandbox_mode=request.sandbox_mode,
        )

    def run(self, prepared: PreparedExecution) -> ExecutionResult:
        if prepared.sandbox_mode == "local":
            # Opt-in by name only: this runs a repository's own test script
            # with the host's privileges, so it is never the default and never
            # reached by a fallback.
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
                    "sandbox": "none (explicitly requested host execution)",
                    "network": "unused (dependencies not installed by the adapter)",
                    "workspace": "read-only intent (test execution only)",
                },
                error=result.error,
            )
            return prepared.result
        # mode="docker" (not "auto"): Docker being unavailable must be an
        # honest error, never a silent reason to run untrusted code here.
        sandbox_result = run_sandboxed(
            prepared.command,
            workspace=prepared.workdir,
            timeout=prepared.timeout,
            mode="docker",
            profile=NODE_PROFILE,
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
                "image": _node_image(),
                "workspace_mount": "ro (no writable sub-mount; source tree immutable)",
            },
            error=sandbox_result.error,
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
                "test_counts": parse_node_test_summary(combined),
            },
        )

    def cleanup(self, prepared: PreparedExecution) -> None:
        """Cleanup boundary: a no-op. node_modules is pipeline/user-owned and
        must never be deleted by the adapter."""
        return None


# ── Planned adapters (matrix only; detect raises, per guide §14 task 10) ──


def detect_java_gradle(repo: RepositorySnapshot) -> RuntimeProfile:
    raise AdapterNotImplemented(
        "Java/Gradle adapter is planned (compatibility matrix status=planned); "
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
        test_runner="jest | vitest | node:test",
        status="已支持 (Docker 沙箱)",
        image=NodeAdapter.IMAGE,
        image_digest=NodeAdapter.IMAGE_DIGEST,
        toolchain=NodeAdapter.TOOLCHAIN,
        offline_policy=NodeAdapter.OFFLINE_POLICY,
        known_limits=NodeAdapter.KNOWN_LIMITS,
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
            NodeAdapter(),
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
