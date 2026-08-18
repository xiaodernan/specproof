"""M1 execution loop (design doc §4.4 + 附录 B): plan -> execute -> verify.

For each plan step the success_criteria is evaluated mechanically:
  compile    -> python -m compileall -q on the target files, exit code 0
  test_green -> python -m pytest -q on the workspace, exit code 0
  grep       -> value="" = readability check over target_files; a non-empty
                value must occur in every target file

A failing step enters the diagnose-fix iteration: a deterministic
"expected/actual" rule template extracts the comparison from the failure
output, then an EXPLICITLY INJECTED fix rule (registry / --fix-module) is
applied. M1 has no LLM: a failing step without an injected fix fails
honestly, it never invents one. The same error signature three times in a
row marks the step stuck and the task STUCK. Iteration / tool-call / time
budgets stop the loop as FAILED / EXPIRED with the reason on record.

checkpoint.json gains one entry per iteration (atomically rewritten);
report.json is the terminal artifact (schema per 附录 B); resume continues
after the last green step recorded in checkpoint.json.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .budget import Budget
from .editor import EditError, Editor
from .executor import ExecResult, Executor, extract_pytest_failed_tests
from .planner import CraftPlanError, Plan, Step, classify_task, write_json_atomic
from .spec import TaskSpec

FixFunction = Callable[[Editor, Step, str], list[str]]


def default_job_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"craft-{stamp}-{secrets.token_hex(4)}"


class CraftLoopError(RuntimeError):
    """Loop state or artifact is unusable."""


class _GateError(Exception):
    """Internal budget gate carrying the terminal outcome and reason."""

    def __init__(self, outcome: str, reason: str) -> None:
        super().__init__(reason)
        self.outcome = outcome
        self.reason = reason


@dataclass
class StepState:
    step: Step
    status: str = "pending"  # pending | green | failed | stuck
    iterations: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.step.id,
            "kind": self.step.kind,
            "status": self.status,
            "iterations": self.iterations,
            "evidence": dict(self.evidence),
        }


_ASSERT_EQ_RE = re.compile(r"^\s*E\s+assert\s+(.+?)\s*==\s*(.+?)\s*$", re.MULTILINE)


def diagnose_failure(step: Step, result: ExecResult | None, note: str = "") -> str:
    """Deterministic diagnosis rule templates (expected/actual extraction).

    M1 never pretends to reason: it only extracts a comparison from real
    failure output through fixed regex templates and falls back to the
    output tail.
    """
    tail = result.output_tail if result is not None else ""
    match = _ASSERT_EQ_RE.search(tail)
    if match:
        actual = match.group(1).strip()
        expected = match.group(2).strip()
        return f"[规则模板] pytest 断言失败 — 预期值 == 实际值: assert {actual} == {expected}"
    for pattern, label in (
        (r"SyntaxError:\s*(.+)", "语法错误"),
        (r"(?:ModuleNotFoundError|ImportError):\s*(.+)", "导入错误"),
        (r"NameError:\s*(.+)", "名称错误"),
        (r"AssertionError(?::\s*(.+))?", "断言失败"),
    ):
        found = re.search(pattern, tail)
        if found:
            detail = found.group(1).strip() if found.lastindex else ""
            return f"[规则模板] {label}: {detail}"
    if tail:
        return f"[规则模板] 无更细规则可匹配, 失败输出尾部: {tail[-500:]}"
    return f"[规则模板] 无命令输出 (读取/grep 类检查失败): {note}"


class CraftLoop:
    """In-memory M1 loop over a deterministic plan (no MySQL — that is M4)."""

    def __init__(
        self,
        spec: TaskSpec,
        plan: Plan,
        workspace: str | Path,
        *,
        budget: Budget | None = None,
        job_id: str | None = None,
        artifact_dir: str | Path | None = None,
        fix_registry: dict[str, FixFunction] | None = None,
        exec_mode: str | None = None,
        exec_timeout: int = 600,
        started_at: float | None = None,
        now_fn: Callable[[], float] | None = None,
        states: list[StepState] | None = None,
        checkpoint_entries: list[dict[str, Any]] | None = None,
        total_iterations: int = 0,
        exec_calls: int = 0,
        task_key: str | None = None,
    ) -> None:
        if plan.mode != "deterministic":
            raise CraftLoopError(f"M1 循环只支持 deterministic 计划 (plan.mode={plan.mode!r})")
        self.spec = spec
        self.plan = plan
        self.workspace = Path(workspace)
        self.budget = budget or Budget.from_env()
        self.job_id = job_id or default_job_id()
        self.artifact_dir = (
            Path(artifact_dir)
            if artifact_dir is not None
            else self.workspace / ".specraft" / "jobs" / self.job_id
        )
        registry = dict(fix_registry or {})
        for key, fix in registry.items():
            if not callable(fix):
                raise CraftLoopError(f"fix_registry[{key!r}] 不是可调用对象")
        self.fix_registry = registry
        self.task_key = task_key or classify_task(spec)
        self.exec_mode = exec_mode
        self.exec_timeout = exec_timeout
        self.now_fn = now_fn or time.time
        self.started_at = started_at if started_at is not None else self.now_fn()
        self.deadline = self.started_at + self.budget.timeout_minutes * 60.0
        self.editor = Editor(
            self.workspace,
            backup_dir=self.artifact_dir / "backup",
            audit_path=self.artifact_dir / "audit.jsonl",
        )
        self.executor = Executor(self.workspace, mode=exec_mode, timeout=exec_timeout)
        self.states = states or [StepState(step=step) for step in plan.steps]
        if len(self.states) != len(plan.steps):
            raise CraftLoopError("states 数量与计划步骤数不一致")
        self.checkpoint_entries: list[dict[str, Any]] = list(checkpoint_entries or [])
        self.total_iterations = total_iterations
        self.exec_calls = exec_calls
        self.last_green_step = ""

    @property
    def tool_calls_used(self) -> int:
        return self.exec_calls + len(self.editor.audit)

    # -- gates -----------------------------------------------------------

    def _time_gate(self, state: StepState) -> None:
        if self.now_fn() >= self.deadline:
            reason = (
                f"时间预算超限 ({self.budget.timeout_minutes} 分钟): 任务 deadline 已到, "
                f"已用 {round(self.now_fn() - self.started_at, 1)}s"
            )
            state.evidence["reason"] = reason
            raise _GateError("EXPIRED", reason)

    def _tool_gate(self, state: StepState) -> None:
        if self.tool_calls_used > self.budget.max_tool_calls:
            reason = (
                f"工具调用预算超限 (max_tool_calls={self.budget.max_tool_calls}, "
                f"已用 {self.tool_calls_used})"
            )
            state.evidence["reason"] = reason
            raise _GateError("FAILED", reason)

    # -- loop ------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.plan.save(self.artifact_dir / "plan.json")
        for index, step in enumerate(self.plan.steps):
            state = self.states[index]
            if state.status == "green":
                continue
            try:
                self._time_gate(state)
            except _GateError as gate:
                state.evidence["reason"] = gate.reason
                return self._finish(gate.outcome)
            outcome = self._run_step(step, state)
            if outcome != "green":
                return self._finish(outcome)
        return self._finish("DONE")

    def _run_step(self, step: Step, state: StepState) -> str:
        try:
            ok, evidence, result = self._check_criteria(step, state)
        except _GateError as gate:
            state.evidence["reason"] = gate.reason
            return gate.outcome
        if ok:
            state.status = "green"
            state.evidence = evidence
            self.last_green_step = step.id
            self._checkpoint(
                step_id=step.id,
                iteration=0,
                diagnosis="",
                edits_applied=[],
                build_result=self._result_dict(result),
                verdict="green",
            )
            return "green"
        attempts = 0
        last_signature = ""
        consecutive = 0
        while True:
            try:
                self._time_gate(state)
            except _GateError as gate:
                state.evidence["reason"] = gate.reason
                return gate.outcome
            if self.total_iterations >= self.budget.max_iterations:
                state.status = "failed"
                reason = f"迭代预算超限 (max_iterations={self.budget.max_iterations})"
                state.evidence["reason"] = reason
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=reason,
                    edits_applied=[],
                    build_result=self._result_dict(result),
                    verdict="progress",
                )
                return "FAILED"
            attempts += 1
            self.total_iterations += 1
            diagnosis = diagnose_failure(step, result, note=evidence.get("reason", ""))
            fix = self._lookup_fix(step)
            if fix is None:
                state.status = "failed"
                reason = (
                    f"M1 确定性模式未注入步骤 {step.id} 的 fix 规则 (--fix-module), "
                    "无法自动修复; 不假装智能"
                )
                state.evidence["reason"] = reason
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=diagnosis,
                    edits_applied=[],
                    build_result=self._result_dict(result),
                    verdict="progress",
                )
                return "FAILED"
            try:
                edited: list[str] = fix(self.editor, step, diagnosis)
            except EditError as exc:
                edited = []
                diagnosis = f"[规则模板] fix 函数抛错 (编辑被拒): {exc}"
            if not isinstance(edited, list) or not all(isinstance(p, str) for p in edited):
                state.status = "failed"
                state.evidence["reason"] = "fix 函数返回类型错误: 应为 list[str]"
                return "FAILED"
            try:
                self._tool_gate(state)
                ok, evidence, result = self._check_criteria(step, state)
            except _GateError as gate:
                state.evidence["reason"] = gate.reason
                return gate.outcome
            if ok:
                state.status = "green"
                state.evidence = evidence
                state.iterations = attempts
                self.last_green_step = step.id
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=diagnosis,
                    edits_applied=list(edited),
                    build_result=self._result_dict(result),
                    verdict="green",
                )
                return "green"
            signature = self._error_signature(step, result)
            if signature == last_signature:
                consecutive += 1
            else:
                last_signature = signature
                consecutive = 1
            rerun_diagnosis = diagnose_failure(step, result, note=evidence.get("reason", ""))
            if consecutive >= 3:
                state.status = "stuck"
                state.iterations = attempts
                state.evidence["reason"] = (
                    f"同类错误连续 {consecutive} 次, 判定 stuck (签名: {signature[:160]})"
                )
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=rerun_diagnosis,
                    edits_applied=list(edited),
                    build_result=self._result_dict(result),
                    verdict="stuck",
                )
                return "STUCK"
            self._checkpoint(
                step_id=step.id,
                iteration=attempts,
                diagnosis=rerun_diagnosis,
                edits_applied=list(edited),
                build_result=self._result_dict(result),
                verdict="progress",
            )

    # -- criteria --------------------------------------------------------

    def _check_criteria(
        self, step: Step, state: StepState
    ) -> tuple[bool, dict[str, Any], ExecResult | None]:
        criteria = step.success_criteria
        if criteria.type == "compile":
            if not step.target_files:
                return (
                    True,
                    {"check": "compile", "note": "无目标文件, 跳过编译 (M1 确定性骨架)"},
                    None,
                )
            result = self._exec(["python", "-m", "compileall", "-q", *step.target_files], state)
            return (
                result.exit_code == 0,
                {
                    "check": "compile",
                    "exit_code": result.exit_code,
                    "mode": result.mode,
                    "output_tail": result.output_tail,
                },
                result,
            )
        if criteria.type == "test_green":
            result = self._exec(["python", "-m", "pytest", "-q"], state)
            return (
                result.exit_code == 0,
                {
                    "check": "test_green",
                    "exit_code": result.exit_code,
                    "failed_tests": extract_pytest_failed_tests(
                        f"{result.stdout}\n{result.stderr}"
                    ),
                    "mode": result.mode,
                    "output_tail": result.output_tail,
                },
                result,
            )
        contents: dict[str, str] = {}
        for target in step.target_files:
            try:
                lines = self.editor.read_file(target)
            except EditError as exc:
                return (
                    False,
                    {"check": "grep", "reason": f"目标文件不可读: {target} ({exc})"},
                    None,
                )
            contents[target] = "\n".join(line for _, line in lines)
        if not criteria.value:
            return (
                True,
                {
                    "check": "grep",
                    "note": f"可读性检查通过: {sorted(contents)} (M1 不注入上下文)",
                },
                None,
            )
        missing = [t for t in step.target_files if criteria.value not in contents[t]]
        if missing:
            return (
                False,
                {"check": "grep", "reason": f"断言值 {criteria.value!r} 未出现在: {missing}"},
                None,
            )
        return (
            True,
            {
                "check": "grep",
                "note": f"断言值 {criteria.value!r} 命中全部目标文件 {sorted(contents)}",
            },
            None,
        )

    def _exec(self, command: list[str], state: StepState) -> ExecResult:
        self._time_gate(state)
        self.exec_calls += 1
        self._tool_gate(state)
        return self.executor.run(command, timeout=self.exec_timeout)

    # -- diagnosis / fix ---------------------------------------------------

    def _lookup_fix(self, step: Step) -> FixFunction | None:
        for key in (step.id, step.kind, self.task_key, "*"):
            candidate = self.fix_registry.get(key)
            if candidate is not None:
                return candidate
        return None

    @staticmethod
    def _error_signature(step: Step, result: ExecResult | None) -> str:
        if result is None:
            return f"{step.id}|<no-exec-output>"
        match = _ASSERT_EQ_RE.search(result.output_tail)
        core = match.group(0).strip() if match else result.output_tail[-160:].strip()
        return f"{step.id}|{core}"

    # -- artifacts ----------------------------------------------------------

    @staticmethod
    def _result_dict(result: ExecResult | None, note: str = "") -> dict[str, Any]:
        if result is None:
            return {"exit_code": -1, "failed_tests": [], "log_tail": note[:1000]}
        return {
            "exit_code": result.exit_code,
            "failed_tests": extract_pytest_failed_tests(f"{result.stdout}\n{result.stderr}"),
            "log_tail": result.output_tail[-1000:],
        }

    def _checkpoint(
        self,
        *,
        step_id: str,
        iteration: int,
        diagnosis: str,
        edits_applied: list[str],
        build_result: dict[str, Any],
        verdict: str,
    ) -> None:
        entry = {
            "job_id": self.job_id,
            "step_id": step_id,
            "iteration": iteration,
            "diagnosis": diagnosis,
            "edits_applied": list(edits_applied),
            "build_result": build_result,
            "verdict": verdict,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.checkpoint_entries.append(entry)
        payload = {
            "job_id": self.job_id,
            "workspace": str(self.workspace),
            "task_key": self.task_key,
            "last_green_step": self.last_green_step,
            "entries": self.checkpoint_entries,
        }
        try:
            write_json_atomic(self.artifact_dir / "checkpoint.json", payload)
        except CraftPlanError as exc:
            raise CraftLoopError(f"checkpoint 写入失败: {exc}") from exc

    def _finish(self, result: str) -> dict[str, Any]:
        changed_files = sorted(
            {
                entry.path
                for entry in self.editor.audit
                if entry.action in ("write", "edit", "move", "delete")
            }
        )
        elapsed = self.now_fn() - self.started_at
        report: dict[str, Any] = {
            "job_id": self.job_id,
            "mode": "deterministic",
            "result": result,
            "steps": [state.to_dict() for state in self.states],
            "diff_stat": {"files_changed": len(changed_files), "files": changed_files},
            "self_verify": {
                "status": "not_implemented",
                "note": "自校验层 (craft/verify.py) 为 M3 范围, M1 未接线 "
                "(--no-self-verify 为当前默认)",
            },
            "budget_used": {
                "tokens": 0,
                "iterations": self.total_iterations,
                "seconds": round(elapsed, 1),
            },
            "audit_trail": [entry.to_dict() for entry in self.editor.audit],
        }
        try:
            write_json_atomic(self.artifact_dir / "report.json", report)
        except CraftPlanError as exc:
            raise CraftLoopError(f"report 写入失败: {exc}") from exc
        return report

    @classmethod
    def from_checkpoint(
        cls,
        artifact_dir: str | Path,
        *,
        fix_registry: dict[str, FixFunction] | None = None,
        budget: Budget | None = None,
        exec_mode: str | None = None,
        exec_timeout: int = 600,
    ) -> CraftLoop:
        """In-memory resume interface: rebuild the loop from .specraft
        artifacts and continue after the last green step (M1: no MySQL)."""
        directory = Path(artifact_dir)
        try:
            plan_data = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
            checkpoint_data = json.loads(
                (directory / "checkpoint.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise CraftLoopError(f"无法读取作业产物 ({directory}): {exc}") from exc
        plan = Plan.from_dict(plan_data)
        if not isinstance(checkpoint_data, dict):
            raise CraftLoopError("checkpoint.json 顶层必须是对象")
        job_id = checkpoint_data.get("job_id")
        workspace_raw = checkpoint_data.get("workspace")
        task_key = checkpoint_data.get("task_key")
        if not isinstance(job_id, str) or not isinstance(workspace_raw, str):
            raise CraftLoopError("checkpoint.json 缺少 job_id/workspace 字段")
        if not isinstance(task_key, str):
            task_key = None
        entries_raw = checkpoint_data.get("entries", [])
        if not isinstance(entries_raw, list):
            raise CraftLoopError("checkpoint.json 的 entries 应为数组")
        entries = [entry for entry in entries_raw if isinstance(entry, dict)]
        last_green = checkpoint_data.get("last_green_step") or ""
        states = [StepState(step=step) for step in plan.steps]
        green_index = -1
        for index, step in enumerate(plan.steps):
            if step.id == last_green:
                green_index = index
        for index in range(green_index + 1):
            states[index].status = "green"
            states[index].evidence = {
                "resumed": True,
                "note": "从 checkpoint 恢复: 该步骤上一轮已绿, 不重跑",
            }
        total_iterations = sum(int(entry.get("iteration", 0)) for entry in entries)
        spec = TaskSpec(title=plan.task_title, description="")
        loop = cls(
            spec,
            plan,
            Path(workspace_raw),
            budget=budget,
            job_id=job_id,
            artifact_dir=directory,
            fix_registry=fix_registry,
            exec_mode=exec_mode,
            exec_timeout=exec_timeout,
            states=states,
            checkpoint_entries=entries,
            total_iterations=total_iterations,
            task_key=task_key,
        )
        loop.last_green_step = str(last_green)
        return loop
