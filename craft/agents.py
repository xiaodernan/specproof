"""Parallel read-only subagent runner (W34 task 9).

Subagents (roles explorer / tester / security) run CONCURRENTLY through
asyncio.gather, each constrained to the ToolRegistry's readonly risk tier
ONLY. Enforcement lives at dispatch level: ReadonlyToolSurface refuses any
tool whose registered risk is not "readonly", and ParallelRunner.validate
rejects any spec whose tool_allowlist names an unknown or non-readonly tool
BEFORE any agent starts (fail-closed). apply_patch / create_file / run_* are
structurally impossible: they are low_write / controlled_exec, never
readonly.

Shared-write safety: every spec declares the files it wants to write
(write_set); overlapping write sets across specs reject the whole run
before start (fail-closed). Read-only access to the repo is unrestricted.

Budget/timeout: the runner enforces the per-agent wall-clock timeout with
asyncio.wait_for; the token budget travels through AgentContext.budget and
is the injected executor's contract (the runner can never count LLM
tokens). Isolation: one agent raising does not kill the others — each
coroutine is wrapped and its error captured as an "error" outcome.

The runner takes an injected async callable (AgentExecutorFn) and never
hardwires craft/llm.py or any provider: tests inject fakes — no network,
no live LLM, no Docker.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schemas import ToolResult
from .tools import ToolRegistry

AGENT_ROLES: tuple[str, ...] = ("explorer", "tester", "security")


class ParallelAgentError(RuntimeError):
    """Base error of the parallel readonly lane."""


class ParallelValidationError(ParallelAgentError):
    """Reject-before-start: allowlist risk, write-set overlap, caps, shapes."""


class ReadonlyViolationError(ParallelAgentError):
    """Dispatch-level refusal of a non-readonly (or unlisted) tool."""


@dataclass(frozen=True)
class SubAgentSpec:
    """One subagent: identity, role, task, readonly tool allowlist, budget."""

    name: str
    role: str
    task: str
    tool_allowlist: frozenset[str] = frozenset()
    budget: dict[str, int] = field(default_factory=dict)
    write_set: frozenset[str] = frozenset()
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("SubAgentSpec.name 不能为空")
        if self.role not in AGENT_ROLES:
            raise ValueError(f"SubAgentSpec.role 非法: {self.role!r} (仅 {list(AGENT_ROLES)})")
        if self.timeout <= 0:
            raise ValueError("SubAgentSpec.timeout 必须 > 0")
        for key, amount in self.budget.items():
            if amount < 0:
                raise ValueError(f"SubAgentSpec.budget[{key!r}] 不能为负数")


class ReadonlyToolSurface:
    """The only dispatch door an agent gets: readonly-tier tools, allowlist-gated."""

    def __init__(self, registry: ToolRegistry, allowlist: Collection[str] = ()) -> None:
        self._registry = registry
        self._allowlist = frozenset(allowlist)

    def list_tools(self) -> list[str]:
        """Readonly registry tools within the allowlist (empty allowlist = none)."""
        names: list[str] = []
        for name in self._registry.tool_names():
            spec = self._registry.get(name)
            if spec is None or spec.risk != "readonly":
                continue
            if name not in self._allowlist:
                continue
            names.append(name)
        return sorted(names)

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Dispatch one tool call through the readonly gate (fail-closed)."""
        if name not in self._allowlist:
            raise ReadonlyViolationError(
                f"工具 {name!r} 不在该代理的 tool_allowlist 内, 拒绝派发 (fail-closed)"
            )
        spec = self._registry.get(name)
        if spec is None:
            raise ReadonlyViolationError(f"工具 {name!r} 未注册, 拒绝派发")
        if spec.risk != "readonly":
            raise ReadonlyViolationError(
                f"工具 {name!r} risk={spec.risk!r} 非 readonly, 只读车道拒绝派发 (fail-closed)"
            )
        return self._registry.dispatch(self._registry.build_tool_call(name, arguments))


@dataclass(frozen=True)
class AgentContext:
    """What one agent executor receives: workspace, readonly surface, budget."""

    workspace: Path
    tools: ReadonlyToolSurface
    budget: dict[str, int]


@dataclass(frozen=True)
class AgentRunResult:
    """One agent's terminal outcome (executor-authored; runner stamps timing)."""

    agent: str
    outcome: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "outcome": self.outcome,
            "findings": [dict(finding) for finding in self.findings],
            "tokens": self.tokens,
            "duration_ms": self.duration_ms,
        }


AgentExecutorFn = Callable[[SubAgentSpec, AgentContext], Awaitable[AgentRunResult]]


@dataclass(frozen=True)
class ParallelReport:
    """Aggregate of every agent's outcome plus the wall-clock total."""

    agents: tuple[AgentRunResult, ...]
    duration_ms: int

    @property
    def overall(self) -> str:
        outcomes = {entry.outcome for entry in self.agents}
        if not outcomes:
            return "error"
        return "ok" if outcomes == {"ok"} else "failed"

    @property
    def summary_line(self) -> str:
        """Machine-greppable single line: 'PARALLEL: overall=... agents=N <outcome=count>...'."""
        counts: dict[str, int] = {}
        for entry in self.agents:
            counts[entry.outcome] = counts.get(entry.outcome, 0) + 1
        breakdown = " ".join(f"{name}={counts[name]}" for name in sorted(counts))
        return (
            f"PARALLEL: overall={self.overall} agents={len(self.agents)} "
            f"{breakdown} duration_ms={self.duration_ms}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "duration_ms": self.duration_ms,
            "agents": [entry.to_dict() for entry in self.agents],
            "summary": self.summary_line,
        }


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


@dataclass
class ParallelRunner:
    """Concurrent readonly subagent runner with fail-closed preflight checks."""

    registry: ToolRegistry
    executor: AgentExecutorFn
    max_agents: int = 8

    def __post_init__(self) -> None:
        if self.max_agents < 1:
            raise ValueError("max_agents 必须 ≥ 1")

    def validate(self, specs: Sequence[SubAgentSpec]) -> None:
        """Reject-before-start: empty/duplicates/N cap, allowlist risks, write overlap."""
        ordered = list(specs)
        if not ordered:
            raise ParallelValidationError("specs 为空, 拒绝启动 (fail-closed)")
        if len(ordered) > self.max_agents:
            raise ParallelValidationError(
                f"代理数 {len(ordered)} 超过并发上限 {self.max_agents} (fail-closed)"
            )
        seen: set[str] = set()
        owners: dict[str, str] = {}
        for spec in ordered:
            if spec.name in seen:
                raise ParallelValidationError(f"代理名重复: {spec.name!r} (fail-closed)")
            seen.add(spec.name)
            for tool in sorted(spec.tool_allowlist):
                registered = self.registry.get(tool)
                if registered is None:
                    raise ParallelValidationError(
                        f"代理 {spec.name} allowlist 含未注册工具 {tool!r} (fail-closed)"
                    )
                if registered.risk != "readonly":
                    raise ParallelValidationError(
                        f"代理 {spec.name} allowlist 工具 {tool!r} risk={registered.risk!r} "
                        "非 readonly, 只读车道拒绝 (fail-closed)"
                    )
            for path in spec.write_set:
                normalized = path.replace("\\", "/")
                owner = owners.get(normalized)
                if owner is not None:
                    raise ParallelValidationError(
                        f"写集合冲突: {owner} 与 {spec.name} 都声明写 {normalized!r} (fail-closed)"
                    )
                owners[normalized] = spec.name

    async def run(self, specs: Sequence[SubAgentSpec]) -> ParallelReport:
        """Validate, then gather every agent concurrently with isolated capture."""
        self.validate(specs)
        ordered = list(specs)
        started = time.perf_counter()
        results = await asyncio.gather(*(self._run_one(spec) for spec in ordered))
        return ParallelReport(
            agents=tuple(results), duration_ms=round((time.perf_counter() - started) * 1000)
        )

    async def _run_one(self, spec: SubAgentSpec) -> AgentRunResult:
        context = AgentContext(
            workspace=self.registry.workspace,
            tools=ReadonlyToolSurface(self.registry, spec.tool_allowlist),
            budget=dict(spec.budget),
        )
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(self.executor(spec, context), timeout=spec.timeout)
        except TimeoutError:
            return AgentRunResult(spec.name, "timed_out", duration_ms=_elapsed_ms(started))
        except Exception as exc:
            return AgentRunResult(
                spec.name,
                "error",
                findings=[{"kind": "agent_crash", "description": f"{type(exc).__name__}: {exc}"}],
                duration_ms=_elapsed_ms(started),
            )
        if not isinstance(result, AgentRunResult):
            return AgentRunResult(
                spec.name,
                "error",
                findings=[
                    {
                        "kind": "invalid_executor_result",
                        "description": (
                            f"executor 返回非法类型 {type(result).__name__}, 期望 AgentRunResult"
                        ),
                    }
                ],
                duration_ms=_elapsed_ms(started),
            )
        if result.agent != spec.name:
            return AgentRunResult(
                spec.name,
                "error",
                findings=[
                    {
                        "kind": "agent_mismatch",
                        "description": (
                            f"executor 结果 agent={result.agent!r} 与 spec {spec.name!r} 不符"
                        ),
                    }
                ],
                duration_ms=_elapsed_ms(started),
            )
        return AgentRunResult(
            spec.name, result.outcome, list(result.findings), result.tokens, _elapsed_ms(started)
        )


__all__ = [
    "AGENT_ROLES",
    "AgentContext",
    "AgentExecutorFn",
    "AgentRunResult",
    "ParallelAgentError",
    "ParallelReport",
    "ParallelRunner",
    "ParallelValidationError",
    "ReadonlyToolSurface",
    "ReadonlyViolationError",
    "SubAgentSpec",
]
