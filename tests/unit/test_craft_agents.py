"""craft/agents.py unit tests — parallel read-only subagent runner (W34 task 9).

Proves, with fakes only (no network, no live LLM, no Docker):
  (a) concurrent execution genuinely overlaps — two slow fake agents finish
      in less than the sum of their sleeps (asyncio event-based);
  (b) a write / controlled-exec tool in a tool_allowlist is rejected before
      start (fail-closed), and the dispatch surface refuses non-readonly
      tools at call time;
  (c) overlapping declared write sets across agents reject the run before
      start (fail-closed); disjoint write sets run fine;
  (d) one agent crashing does not kill the others (isolated error capture);
  (e) per-agent wall-clock timeout and token budget flow are honored;
  plus surface/list/validation/report contract coverage.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from craft.agents import (
    AgentContext,
    AgentRunResult,
    ParallelRunner,
    ParallelValidationError,
    ReadonlyToolSurface,
    ReadonlyViolationError,
    SubAgentSpec,
)
from craft.executor import Executor
from craft.tools import ToolRegistry


def make_registry(tmp_path: Path) -> ToolRegistry:
    return ToolRegistry(tmp_path, executor=Executor(tmp_path, mode="local"))


def make_spec(
    name: str = "agent-a",
    *,
    role: str = "explorer",
    allowlist: tuple[str, ...] = ("read_file",),
    write_set: tuple[str, ...] = (),
    budget: dict[str, int] | None = None,
    timeout: float = 5.0,
) -> SubAgentSpec:
    return SubAgentSpec(
        name=name,
        role=role,
        task="inspect",
        tool_allowlist=frozenset(allowlist),
        write_set=frozenset(write_set),
        budget=dict(budget or {}),
        timeout=timeout,
    )


async def ok_executor(spec: SubAgentSpec, context: AgentContext) -> AgentRunResult:
    return AgentRunResult(spec.name, "ok")


def make_runner(tmp_path: Path, executor: Any = None, **kwargs: Any) -> ParallelRunner:
    chosen = executor if executor is not None else ok_executor
    return ParallelRunner(make_registry(tmp_path), chosen, **kwargs)


# -- spec validation --------------------------------------------------------------


def test_spec_rejects_unknown_role() -> None:
    with pytest.raises(ValueError, match="role"):
        make_spec(role="wizard")


def test_spec_rejects_bad_name_timeout_budget() -> None:
    with pytest.raises(ValueError, match="name"):
        SubAgentSpec(name="  ", role="explorer", task="t")
    with pytest.raises(ValueError, match="timeout"):
        make_spec(timeout=0)
    with pytest.raises(ValueError, match="budget"):
        make_spec(budget={"tokens": -1})


# -- dispatch surface (readonly tier only) -----------------------------------------


def test_surface_lists_only_readonly_allowlisted_tools(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    surface = ReadonlyToolSurface(registry, {"read_file"})
    assert surface.list_tools() == ["read_file"]
    mixed = ReadonlyToolSurface(registry, {"read_file", "apply_patch", "run_test"})
    assert mixed.list_tools() == ["read_file"]
    assert ReadonlyToolSurface(registry, ()).list_tools() == []


def test_surface_dispatches_readonly_tool(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("line one\n", encoding="utf-8")
    surface = ReadonlyToolSurface(make_registry(tmp_path), {"read_file"})
    result = surface.call("read_file", {"path": "f.txt"})
    assert result.status == "ok"
    assert "read_file" in result.summary
    assert "line one" in result.output_head


def test_surface_rejects_nonreadonly_tool_at_dispatch(tmp_path: Path) -> None:
    apply_surface = ReadonlyToolSurface(make_registry(tmp_path), {"apply_patch"})
    with pytest.raises(ReadonlyViolationError, match="非 readonly"):
        apply_surface.call("apply_patch", {"path": "f.txt", "old": "a", "new": "b"})
    run_surface = ReadonlyToolSurface(make_registry(tmp_path), {"run_test"})
    with pytest.raises(ReadonlyViolationError, match="非 readonly"):
        run_surface.call("run_test", {"command": ["python", "-m", "pytest"]})


def test_surface_rejects_unlisted_and_unknown_tools(tmp_path: Path) -> None:
    surface = ReadonlyToolSurface(make_registry(tmp_path), {"read_file"})
    with pytest.raises(ReadonlyViolationError, match="allowlist"):
        surface.call("grep", {"pattern": "x"})
    unknown_surface = ReadonlyToolSurface(make_registry(tmp_path), {"shell"})
    with pytest.raises(ReadonlyViolationError, match="未注册"):
        unknown_surface.call("shell", {})


# -- reject-before-start validation --------------------------------------------------


async def test_write_tool_in_allowlist_rejected_before_start(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    write_and_exec_tools = (
        "apply_patch", "create_file", "run_test", "run_build", "run_lint", "run_typecheck"
    )
    for bad_tool in write_and_exec_tools:
        with pytest.raises(ParallelValidationError, match="非 readonly"):
            await runner.run([make_spec(allowlist=(bad_tool,))])


async def test_unknown_tool_in_allowlist_rejected(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    with pytest.raises(ParallelValidationError, match="未注册"):
        await runner.run([make_spec(allowlist=("sudo",))])


async def test_overlapping_write_sets_rejected_before_start(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    specs = [
        make_spec(name="a", write_set=("out/notes.md",)),
        make_spec(name="b", write_set=("out\\notes.md",)),  # same path, windows form
    ]
    with pytest.raises(ParallelValidationError, match="写集合冲突"):
        await runner.run(specs)


async def test_disjoint_write_sets_accepted(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    specs = [
        make_spec(name="a", write_set=("a.md",)),
        make_spec(name="b", write_set=("b.md",)),
    ]
    report = await runner.run(specs)
    assert report.overall == "ok"
    assert len(report.agents) == 2


async def test_duplicate_names_rejected(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    with pytest.raises(ParallelValidationError, match="重复"):
        await runner.run([make_spec("same"), make_spec("same")])


async def test_agent_cap_rejected(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, max_agents=1)
    with pytest.raises(ParallelValidationError, match="并发上限"):
        await runner.run([make_spec("a"), make_spec("b")])


async def test_empty_specs_rejected(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    with pytest.raises(ParallelValidationError, match="为空"):
        await runner.run([])


# -- (a) concurrency: real overlap ---------------------------------------------------


async def test_concurrent_execution_overlaps(tmp_path: Path) -> None:
    starts: list[float] = []

    async def slow(spec: SubAgentSpec, context: AgentContext) -> AgentRunResult:
        starts.append(time.perf_counter())
        await asyncio.sleep(0.2)
        return AgentRunResult(spec.name, "ok")

    runner = make_runner(tmp_path, executor=slow)
    wall_started = time.perf_counter()
    report = await runner.run([make_spec("a"), make_spec("b")])
    wall = time.perf_counter() - wall_started
    assert report.overall == "ok"
    assert len(report.agents) == 2
    # Serial execution would take >= 0.4s (two 0.2s sleeps); overlap finishes
    # in roughly one sleep. Generous margins for slow CI machines.
    assert wall < 0.35, f"wall={wall:.3f}s (serial?)"
    assert starts[1] - starts[0] < 0.15, "second agent did not start before first finished"


# -- (d) crash isolation -----------------------------------------------------------------


async def test_one_agent_crash_does_not_kill_others(tmp_path: Path) -> None:
    async def flaky(spec: SubAgentSpec, context: AgentContext) -> AgentRunResult:
        if spec.name == "boom":
            raise RuntimeError("agent exploded")
        return AgentRunResult(spec.name, "ok")

    runner = make_runner(tmp_path, executor=flaky)
    report = await runner.run([make_spec("boom"), make_spec("steady")])
    by_name = {entry.agent: entry for entry in report.agents}
    assert by_name["boom"].outcome == "error"
    assert by_name["boom"].findings[0]["kind"] == "agent_crash"
    assert "agent exploded" in by_name["boom"].findings[0]["description"]
    assert by_name["steady"].outcome == "ok"
    assert report.overall == "failed"


# -- (e) budget / timeout ---------------------------------------------------------------


async def test_timeout_is_honored_per_agent(tmp_path: Path) -> None:
    async def slowpoke(spec: SubAgentSpec, context: AgentContext) -> AgentRunResult:
        await asyncio.sleep(0.5)
        return AgentRunResult(spec.name, "ok")

    runner = make_runner(tmp_path, executor=slowpoke)
    report = await runner.run(
        [make_spec("slow", timeout=0.1), make_spec("fast", timeout=2.0)]
    )
    by_name = {entry.agent: entry for entry in report.agents}
    assert by_name["slow"].outcome == "timed_out"
    assert by_name["slow"].duration_ms < 400
    assert by_name["fast"].outcome == "ok"
    assert report.overall == "failed"


async def test_budget_flows_through_context_and_overrun_recorded(tmp_path: Path) -> None:
    seen_budgets: dict[str, dict[str, int]] = {}

    async def budgeted(spec: SubAgentSpec, context: AgentContext) -> AgentRunResult:
        seen_budgets[spec.name] = context.budget
        tokens = context.budget.get("tokens", 0) + 2  # simulates overspend
        return AgentRunResult(spec.name, "budget_exceeded", tokens=tokens)

    runner = make_runner(tmp_path, executor=budgeted)
    report = await runner.run([make_spec("spendy", budget={"tokens": 5})])
    assert seen_budgets["spendy"] == {"tokens": 5}
    entry = report.agents[0]
    assert entry.outcome == "budget_exceeded"
    assert entry.tokens == 7
    assert report.overall == "failed"


# -- executor contract robustness -------------------------------------------------------


async def test_invalid_executor_result_becomes_error(tmp_path: Path) -> None:
    async def garbage(spec: SubAgentSpec, context: AgentContext) -> Any:
        return "not-a-result"

    runner = make_runner(tmp_path, executor=garbage)
    report = await runner.run([make_spec("a")])
    entry = report.agents[0]
    assert entry.outcome == "error"
    assert entry.findings[0]["kind"] == "invalid_executor_result"


async def test_agent_name_mismatch_becomes_error(tmp_path: Path) -> None:
    async def wrong_name(spec: SubAgentSpec, context: AgentContext) -> AgentRunResult:
        return AgentRunResult("someone-else", "ok")

    runner = make_runner(tmp_path, executor=wrong_name)
    report = await runner.run([make_spec("a")])
    entry = report.agents[0]
    assert entry.outcome == "error"
    assert entry.findings[0]["kind"] == "agent_mismatch"


# -- report contract -----------------------------------------------------------------------


async def test_report_overall_and_machine_greppable_summary(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    report = await runner.run(
        [
            make_spec("a", role="explorer"),
            make_spec("b", role="tester"),
            make_spec("c", role="security"),
        ]
    )
    assert report.overall == "ok"
    assert report.summary_line.startswith("PARALLEL: overall=ok")
    assert "agents=3" in report.summary_line
    assert "ok=3" in report.summary_line
    assert report.duration_ms >= 0
    payload = report.to_dict()
    assert payload["overall"] == "ok"
    assert len(payload["agents"]) == 3
    assert payload["summary"] == report.summary_line


async def test_report_mixed_outcomes_overall_failed(tmp_path: Path) -> None:
    async def mixed(spec: SubAgentSpec, context: AgentContext) -> AgentRunResult:
        if spec.name == "okay":
            return AgentRunResult(spec.name, "ok")
        return AgentRunResult(spec.name, "failed", findings=[{"kind": "x"}])

    runner = make_runner(tmp_path, executor=mixed)
    report = await runner.run([make_spec("okay"), make_spec("broken")])
    assert report.overall == "failed"
    assert "failed=1" in report.summary_line
    assert "ok=1" in report.summary_line
