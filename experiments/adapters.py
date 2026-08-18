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
existing capability, re-homed behind the protocol); Java/Gradle, Node,
Python and Go exist as planned matrix rows whose detect functions raise
AdapterNotImplemented — we do NOT claim to support arbitrary projects.
"""

from __future__ import annotations

import os
import platform
import re
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


def _maven_wrapper(workspace: str) -> str:
    """Maven wrapper script path for the local fallback (CreateProcessW on
    Windows resolves relative names against the parent cwd, so the path must
    be absolute — same rule the pre-adapter pipeline already followed)."""
    script = "mvnw.cmd" if platform.system() == "Windows" else "mvnw"
    return os.path.join(workspace, script)


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


def detect_python(repo: RepositorySnapshot) -> RuntimeProfile:
    raise AdapterNotImplemented(
        "Python adapter is planned (compatibility matrix status=planned); "
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
        build_tool="pip/uv",
        test_runner="pytest",
        status="规划 (planned)",
        image="—",
        image_digest="—",
        toolchain="待定 (随实现声明)",
        offline_policy="待定 (离线缓存策略随实现声明)",
        known_limits=("detect 抛 AdapterNotImplemented; 无执行器",),
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
            _PlannedAdapter("Python", detect_python),
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
