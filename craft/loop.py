"""Execution loop (design doc §4.4 + 附录 B): plan -> execute -> verify.

For each plan step the success_criteria is evaluated mechanically:
  compile    -> python -m compileall -q on the target files, exit code 0
  test_green -> python -m pytest -q on the workspace, exit code 0
  grep       -> value="" = readability check over target_files; a non-empty
                value must occur in every target file

A failing step enters the diagnose-fix iteration:
- M1: a deterministic "expected/actual" rule template extracts the
  comparison from the failure output, then an EXPLICITLY INJECTED fix rule
  (registry / --fix-module) is applied. Without an injected fix the step
  fails honestly — it never invents one.
- M2: with an LLMClient, the diagnose template asks the model for a JSON
  edit proposal (apply_edit / write_file); every operation still goes
  through Editor (uniqueness / atomic write / backup / audit). An illegal
  or unparseable proposal fails the step with M1 semantics — never faked.
  A token-budget overrun (BudgetExceeded) becomes an honest FAILED.

The same error signature three times in a row marks the step stuck and the
task STUCK. Iteration / tool-call / time / token budgets stop the loop as
FAILED / EXPIRED with the reason on record. reasoning_content (ADR-017)
stays in memory only — it never reaches checkpoint.json / report.json.

checkpoint.json gains one entry per iteration (atomically rewritten);
report.json is the terminal artifact (schema per 附录 B); resume continues
after the last green step recorded in checkpoint.json.

Task memory (卷 XXI §21.1): the loop keeps a TaskMemory of deterministic
facts — file reads (grep criteria), file writes (edited paths), error
signatures (failed iterations, merged by count), decisions (green/stuck/
terminal verdicts) and budget snapshots. It is written to memory.json
alongside every checkpoint, restored by from_checkpoint, and injected into
the diagnose prompt's variable_data section only (never the stable prefix).
Ctrl-C support (卷 XXI §21.3): interrupt_checkpoint() flushes the in-flight
step as an 'interrupted' checkpoint entry + memory.json; report.json stays
untouched until the task actually finishes. All artifacts
(checkpoint/report/memory) carry no reasoning text (ADR-017).

M3 self-verify (SPECCRAFT_PLAN §4.5): _finish runs craft.verify.self_verify
over the changed files before writing report.json (secret/canary scan +
Java contract checkers, both read-only). A failed gate overrides a DONE
verdict to FAILED with the findings on record; edits are NOT rolled back —
the report says so honestly. --no-self-verify (skip_self_verify=True)
skips the gate and marks report.self_verify.status=skipped.

W113 hardening (real eval evidence docs/eval/swebench-llm-results-v3.json):
- edit anchor (flask-4045): the diagnose/edit-proposal prompt ships the
  current real content of each candidate source file (first 400 lines,
  raw) and instructs the model to quote old strings EXACTLY from it;
  Editor.apply_edit additionally retries a whitespace-normalized line
  match (tabs collapsed, trailing spaces stripped) before rejecting.
- verify target (flask-4992): "assertion appears" grep criteria search
  SOURCE files only — the harness applies hidden tests AFTER craft, so a
  grep against tests/** can never pass; test-only targets FAIL honestly.

W35 gate composition + durable job projection: when the M3 self-verify gate
runs at finish, the full GatePipeline (craft/gates.py, five layered gates)
runs too and its summary is embedded as report.gates — informational only,
the loop does NOT block on it here (craft/accept.py owns the hard closure).
An optional AgentJobStore (storage/agent_jobs.py, W30) turns the loop into
a durable, leaseable job: create/lease on start, renew + set_progress per
step, update_status(result_json=report) at finish, supervisor cancel wins
over a leased worker (CANCELLED terminal is flushed honestly), and
from_checkpoint re-leases per the W30 Integration note. store=None keeps
the original in-memory behavior untouched.

W44 metrics wiring (additive, all OFF by default): an optional
ToolCallSelfCheck validates the M2 JSON Action Envelope through
check_with_retry with the model round-trip injected as the producer
callable (an invalid envelope is never executed; a second invalid one
gives up with the stable registry code); an optional ModelRouter routes
the diagnose path via route("diagnose") with one strong fallback on a
cheap-tier failure; an optional SemanticCache serves cacheable diagnose
prompts; judge_persona=True appends the no-fake-pass persona to the
diagnose system block. All counters land in report.gains (tool-call
attempts/valid/retried/success rate, router fallbacks, cache hits,
judge-persona flag) — zero-filled when nothing is configured.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from providers.base import LLMMessage, LLMResponse
from providers.budget import BudgetExceeded
from providers.judge_persona import build_judge_prompt
from providers.prompt_templates import (
    JSON_ACTION_ENVELOPE_BLOCK,
    SYSTEM_BLOCK,
    TOOL_SCHEMA_BLOCK,
    assemble,
)
from providers.router import ModelRouter, ProviderRoute
from providers.semantic_cache import SemanticCache, cache_key, cacheable
from providers.toolcheck import (
    CODE_PROPOSAL_INVALID,
    EditProposalSelfCheck,
    ProposalParseFailure,
    ToolCallSelfCheck,
    is_test_file_path,
)
from storage.agent_jobs import (
    AgentJobStore,
    InvalidJobTransitionError,
    JobAlreadyExistsError,
    JobStatus,
)

from .budget import Budget
from .editor import EditError, Editor
from .executor import ExecResult, Executor, extract_pytest_failed_tests
from .gates import GatePipeline
from .llm import (
    LLMClient,
    LLMUnavailableError,
    extract_json_object,
    resolve_craft_thinking,
    wrap_data_section,
)
from .memory import MemoryError, TaskMemory
from .planner import CraftPlanError, Plan, Step, classify_task, write_json_atomic
from .schemas import ChangeBundle
from .spec import TaskSpec
from .tools import ToolRegistry
from .verify import self_verify

FixFunction = Callable[[Editor, Step, str], list[str]]


def _prompt_digest(text: str) -> str:
    """sha256 digest of a built prompt (semantic-cache key material)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


class _LLMFixError(RuntimeError):
    """The model's edit proposal was illegal or was refused by the Editor."""


_EDITOR_API_BLOCK: str = """\
可用编辑工具 (所有路径相对仓库根; 绝对路径与 .. 逃逸会被拒绝):
- read_file(path) -> 带行号内容 (目标文件内容已随本提示提供, 通常无需再读);
- write_file(path, content): 整文件原子写 (temp + replace), 已有文件先备份到 .specraft/backup/;
- apply_edit(path, old, new): 精确子串替换; old 必须在文件中恰好出现一次, 否则拒绝且不落盘;
每次编辑都会写入审计日志 (谁/何时/动了什么)。禁止修改测试文件与 spec 明令禁止的文件。
"""

_EDIT_OPS_SCHEMA: str = """\
OUTPUT CONTRACT — respond with exactly one JSON object (no markdown fences,
no prose around the JSON):

{
  "diagnosis": "one sentence: the root cause you identified from the evidence",
  "edits": [
    {"action": "apply_edit", "path": "calc.py", "old": "return x / 2", "new": "return x * 2"},
    {"action": "write_file", "path": "new.py", "new": "full file content"}
  ]
}

Hard rules:
- action is exactly "apply_edit" or "write_file";
- apply_edit requires old/new strings and old must match EXACTLY once in the
  current file content shown above, otherwise the edit is rejected;
- propose only edits the evidence justifies; never touch test files or
  forbidden files; never invent evidence.
"""

# System-prefix output contract for the diagnose-fix call (首跑缺口修复).
# The gateway only honors response_format=json_object when the prompt
# itself names JSON (docs/design/GRAND_PLAN_V2.md), and the previous prompt
# carried a CONFLICTING JSON Action Envelope tail — the model then answered
# with {"action": ...} envelopes that lacked the "edits" array. This block
# is the single authoritative contract in the stable prefix, with a compact
# inline example; the action envelope is NOT appended to this call anymore.
_EDIT_PROPOSAL_OUTPUT_BLOCK: str = (
    """\
EDIT PROPOSAL OUTPUT CONTRACT — your ENTIRE reply must be ONE JSON object
(no markdown fences, no prose around the JSON) with exactly two top-level
keys: "diagnosis" (string, one sentence naming the root cause) and "edits"
(array of edit operations). Compact example:
"""
    + '{"diagnosis": "double() divides instead of multiplying", "edits": '
    '[{"action": "apply_edit", "path": "src/calc.py", '
    '"old": "return x / 2", "new": "return x * 2"}]}\n'
    + """\
Hard rules:
- each edit object has "action" (exactly "apply_edit" or "write_file") and
  a repo-relative "path";
- apply_edit requires string "old"/"new"; quote old strings EXACTLY from
  the file content above — copy the real lines byte-for-byte (indentation
  and inline whitespace included), never reconstruct code from memory; old
  must match EXACTLY once in the current file content, otherwise the edit
  is rejected;
- write_file requires string "new" (the full file content);
- fix only production/source code, never create or modify test files —
  hidden tests are applied by the harness itself;
- propose only edits the evidence justifies; never touch test files or
  forbidden files; never invent evidence.
"""
)


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


def _parse_edit_ops(data: object) -> tuple[str, list[dict[str, Any]]]:
    """Parse the model's edit proposal: {"diagnosis": str, "edits": [...]}
    or a bare [...] array. Illegal shapes raise _LLMFixError — the step
    then fails with M1 semantics instead of pretending.
    """
    explanation = ""
    if isinstance(data, list):
        ops = data
    elif isinstance(data, dict):
        raw_ops = data.get("edits")
        if not isinstance(raw_ops, list):
            raise _LLMFixError("模型输出缺少 edits 数组")
        ops = raw_ops
        raw_explanation = data.get("diagnosis", data.get("explanation", ""))
        if isinstance(raw_explanation, str):
            explanation = raw_explanation.strip()
    else:
        raise _LLMFixError("模型输出顶层必须是 JSON 对象或数组")
    if not all(isinstance(op, dict) for op in ops):
        raise _LLMFixError("编辑操作数组的元素必须是 JSON 对象")
    return explanation, ops


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
        python: str | None = None,
        started_at: float | None = None,
        now_fn: Callable[[], float] | None = None,
        states: list[StepState] | None = None,
        checkpoint_entries: list[dict[str, Any]] | None = None,
        total_iterations: int = 0,
        exec_calls: int = 0,
        task_key: str | None = None,
        client: LLMClient | None = None,
        memory: TaskMemory | None = None,
        skip_self_verify: bool = False,
        tool_registry: ToolRegistry | None = None,
        # W44 metrics wiring — all off by default; passing a self-check /
        # router / cache in is the only way to change behavior.
        tool_call_self_check: ToolCallSelfCheck | None = None,
        router: ModelRouter | None = None,
        semantic_cache: SemanticCache | None = None,
        judge_persona: bool = False,
        store: AgentJobStore | None = None,
        lease_ttl_seconds: float = 900,
    ) -> None:
        if plan.mode not in ("deterministic", "llm"):
            raise CraftLoopError(
                f"循环只支持 deterministic|llm 计划 (plan.mode={plan.mode!r})"
            )
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
        self.tool_registry = tool_registry
        if tool_call_self_check is not None and tool_registry is None:
            raise CraftLoopError(
                "tool_call_self_check 需要 tool_registry: "
                "自检通过的信封必须经注册表执行, 不能直接调用编辑器"
            )
        self.tool_call_self_check = tool_call_self_check
        self.router = router
        self.semantic_cache = semantic_cache
        self.judge_persona = judge_persona
        self._judge_persona_applied = 0
        if tool_registry is not None:
            # One editor for the whole job: registry dispatches and the
            # loop's grep reads share the audit trail, so report.diff_stat,
            # the M3 base snapshots and memory.json stay coherent. Callers
            # should bind the registry's editor to the job artifact dir.
            self.editor = tool_registry.editor
        else:
            self.editor = Editor(
                self.workspace,
                backup_dir=self.artifact_dir / "backup",
                audit_path=self.artifact_dir / "audit.jsonl",
            )
        self.executor = Executor(
            self.workspace, mode=exec_mode, timeout=exec_timeout, python=python
        )
        self.states = states or [StepState(step=step) for step in plan.steps]
        if len(self.states) != len(plan.steps):
            raise CraftLoopError("states 数量与计划步骤数不一致")
        self.checkpoint_entries: list[dict[str, Any]] = list(checkpoint_entries or [])
        self.total_iterations = total_iterations
        self.exec_calls = exec_calls
        self.last_green_step = ""
        self.client = client
        self.llm_calls = 0
        # M3 self-verify hard gate: default ON; --no-self-verify skips it
        # and _finish marks report.self_verify.status=skipped honestly.
        self.skip_self_verify = skip_self_verify
        # Task-level fact memory (卷 XXI §21.1): file reads/writes, error
        # signatures, decisions and budget snapshots — deterministic facts
        # only, never reasoning text (ADR-017). Persisted to memory.json.
        self.memory = memory or TaskMemory()
        # In-flight step for the Ctrl-C flush (卷 XXI §21.3).
        self._current_step: Step | None = None
        self._current_state: StepState | None = None
        # W35 durable job projection (W30 AgentJobStore). store=None keeps the
        # original in-memory behavior; the lease owner is computed at run()
        # time (host:pid:job_id) and must not change within one run.
        self.store = store
        self.lease_ttl_seconds = lease_ttl_seconds
        self._lease_owner = ""

    @property
    def tool_calls_used(self) -> int:
        return self.exec_calls + len(self.editor.audit) + self.llm_calls

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
        self._store_prepare()
        self._store_lease()
        if self.store is not None:
            # supervisor cancel wins over late projections
            with suppress(InvalidJobTransitionError):
                self.store.set_plan(self.job_id, self.plan.to_dict())
        for index, step in enumerate(self.plan.steps):
            state = self.states[index]
            if state.status == "green":
                continue
            if self._store_cancelled(step):
                return self._finish("CANCELLED")
            self._store_renew()
            try:
                self._time_gate(state)
            except _GateError as gate:
                state.evidence["reason"] = gate.reason
                return self._finish(gate.outcome)
            outcome = self._run_step(step, state)
            if outcome != "green":
                return self._finish(outcome)
        return self._finish("DONE")

    # -- durable job projection (W35 / W30 Integration note) -----------------

    def _store_prepare(self) -> None:
        """Job intake: probe-then-create (create raises on duplicates)."""
        if self.store is None:
            return
        if self.store.get(self.job_id) is None:
            # another worker raced us in; the lease below arbitrates
            with suppress(JobAlreadyExistsError):
                self.store.create(self.job_id, json.dumps(self.spec.to_dict()))

    def _store_lease(self) -> None:
        """Acquire the job lease; refusing to run without it is fail-closed."""
        if self.store is None:
            return
        self._lease_owner = f"{socket.gethostname()}:{os.getpid()}:{self.job_id}"
        if not self.store.lease(self.job_id, self._lease_owner, self.lease_ttl_seconds):
            raise CraftLoopError(
                f"作业 {self.job_id} 租约未获取 (被另一 worker 持有或已是终态); 不重复执行"
            )

    def _store_renew(self) -> None:
        """Renew the lease once per step; losing it to another worker aborts."""
        if self.store is None or not self._lease_owner:
            return
        if self.store.renew(self.job_id, self._lease_owner, self.lease_ttl_seconds):
            return
        job = self.store.get(self.job_id)
        if job is not None and job.status == "cancelled":
            return  # the step-loop cancel check flushes the honest exit
        raise CraftLoopError(
            f"作业 {self.job_id} 租约失效 (另一 worker 接管或租约过期); 中止"
        )

    def _store_cancelled(self, step: Step) -> bool:
        """Supervisor cancel check: cancel wins even over a leased worker."""
        if self.store is None:
            return False
        job = self.store.get(self.job_id)
        if job is not None and job.status == "cancelled":
            self._checkpoint(
                step_id=step.id,
                iteration=0,
                diagnosis="supervisor 取消作业 (cancel 优先于租约), 本步骤未执行",
                edits_applied=[],
                build_result={"exit_code": -1, "failed_tests": [], "log_tail": ""},
                verdict="cancelled",
            )
            return True
        return False

    def _store_set_progress(self, step_id: str, iteration: int) -> None:
        """Project the current step into the durable store (per checkpoint)."""
        if self.store is None:
            return
        state = self._current_state
        progress: dict[str, Any] = {
            "status": state.status if state is not None else "pending",
            "iterations": state.iterations if state is not None else iteration,
            "evidence": dict(state.evidence) if state is not None else {},
        }
        # supervisor cancel wins over late projections
        with suppress(InvalidJobTransitionError):
            self.store.set_progress(self.job_id, current_step=step_id, progress=progress)

    def _run_step(self, step: Step, state: StepState) -> str:
        self._current_step = step
        self._current_state = state
        try:
            ok, evidence, result = self._check_criteria(step, state)
        except _GateError as gate:
            state.evidence["reason"] = gate.reason
            return gate.outcome
        if ok:
            state.status = "green"
            state.evidence = evidence
            self.last_green_step = step.id
            self.memory.add("decision", f"步骤 {step.id} 首次检查即 green", step_id=step.id)
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
                if self.client is None:
                    state.status = "failed"
                    if self.plan.mode == "llm":
                        reason = (
                            f"步骤 {step.id} 失败且无注入 fix 规则, 但未提供 LLM 客户端 "
                            "(llm 计划需 --llm 或注入 --fix-module); 不假装智能"
                        )
                    else:
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
                    diagnosis, edited = self._llm_fix(step, result, diagnosis)
                except BudgetExceeded as exc:
                    state.status = "failed"
                    reason = f"LLM token 预算超限: {exc}"
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
                except LLMUnavailableError as exc:
                    state.status = "failed"
                    reason = "LLM unavailable: " + str(exc)
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
                except _LLMFixError as exc:
                    state.status = "failed"
                    reason = f"LLM 编辑提案非法, 按 M1 语义 FAILED: {exc}"
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
            else:
                try:
                    edited = fix(self.editor, step, diagnosis)
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
                self.memory.add(
                    "decision", f"步骤 {step.id} 修复后 green (迭代 {attempts})",
                    step_id=step.id,
                )
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=diagnosis,
                    edits_applied=list(edited),
                    build_result=self._result_dict(result),
                    verdict="green",
                )
                return "green"
            signature = self._error_signature(
                step, result, note=str(evidence.get("reason", ""))
            )
            self.memory.add("error_signature", signature, step_id=step.id)
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
                self.memory.add(
                    "decision",
                    f"步骤 {step.id} stuck: 同类错误签名连续 {consecutive} 次",
                    step_id=step.id,
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
            evidence: dict[str, Any] = {
                "check": "compile",
                "exit_code": result.exit_code,
                "mode": result.mode,
                "output_tail": result.output_tail,
            }
            if result.stderr.strip():
                evidence["stderr_tail"] = result.stderr[-1000:]
            if result.error:
                evidence["error"] = result.error
            return (result.exit_code == 0, evidence, result)
        if criteria.type == "test_green":
            result = self._exec(["python", "-m", "pytest", "-q"], state)
            # 首跑缺口修复: the real stderr tail and the sandbox-level error
            # (spawn failure / venv python missing / timeout) ride the
            # evidence — a failing run_test must never surface as empty.
            evidence = {
                "check": "test_green",
                "exit_code": result.exit_code,
                "failed_tests": extract_pytest_failed_tests(
                    f"{result.stdout}\n{result.stderr}"
                ),
                "mode": result.mode,
                "output_tail": result.output_tail,
            }
            if result.stderr.strip():
                evidence["stderr_tail"] = result.stderr[-1000:]
            if result.error:
                evidence["error"] = result.error
            return (result.exit_code == 0, evidence, result)
        contents: dict[str, str] = {}
        # 诚实不变量 (W113): 断言值类 grep 校验 ("assertion appears") 只搜索
        # 源文件, 永不搜索测试文件 — 隐藏测试由评测框架在 craft 结束之后才
        # 应用到仓库, craft 阶段根本看不见它们, 因此对 tests/** 的断言值
        # 校验永远无法通过 (真实证据: pallets__flask-4992 在
        # tests/test_config.py 上 grep "tomllib" 3 轮后 STUCK)。目标只有
        # 测试文件时诚实 FAILED, 绝不伪造通过。value="" 的可读性检查不
        # 过滤 (不涉及断言值), 保持原语义。
        targets = step.target_files
        excluded_tests: list[str] = []
        if criteria.value:
            excluded_tests = [t for t in step.target_files if is_test_file_path(t)]
            targets = [t for t in step.target_files if not is_test_file_path(t)]
        for target in targets:
            try:
                lines = self.editor.read_file(target)
            except EditError as exc:
                return (
                    False,
                    {"check": "grep", "reason": f"目标文件不可读: {target} ({exc})"},
                    None,
                )
            contents[target] = "\n".join(line for _, line in lines)
            self.memory.add("file_read", target, step_id=step.id)
        if not criteria.value:
            return (
                True,
                {
                    "check": "grep",
                    "note": f"可读性检查通过: {sorted(contents)} (M1 不注入上下文)",
                },
                None,
            )
        if not targets and step.target_files:
            reason = (
                f"断言值 {criteria.value!r} 无源文件可搜索: 目标 "
                f"{sorted(step.target_files)} 均为测试文件 — 隐藏测试由评测框架在 "
                "craft 后施加, craft 阶段不可见; 请只修复源文件使隐藏测试通过"
            )
            return (False, {"check": "grep", "reason": reason}, None)
        missing = [t for t in targets if criteria.value not in contents[t]]
        if missing:
            reason = f"断言值 {criteria.value!r} 未出现在源文件: {missing}"
            if excluded_tests:
                reason += (
                    f"; 已排除测试文件 {sorted(excluded_tests)} "
                    "(隐藏测试由评测框架在 craft 后施加, 不做断言校验)"
                )
            return (False, {"check": "grep", "reason": reason}, None)
        note = f"断言值 {criteria.value!r} 命中全部目标源文件 {sorted(contents)}"
        if excluded_tests:
            note += (
                f"; 已排除测试文件 {sorted(excluded_tests)} "
                "(隐藏测试由评测框架在 craft 后施加, 不做断言校验)"
            )
        return (True, {"check": "grep", "note": note}, None)

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

    def _llm_fix(
        self, step: Step, result: ExecResult | None, diagnosis: str
    ) -> tuple[str, list[str]]:
        """M2 diagnose-fix: the model proposes JSON edit operations — or,
        with a ToolCallSelfCheck configured, one validated JSON Action
        Envelope — and the Editor enforces uniqueness / atomic write /
        backup / audit exactly as in M1. Returns (diagnosis_text,
        edited_paths).

        W44 wiring, all OFF by default (an unconfigured loop behaves
        identically to the pre-W44 one):
        - judge_persona=True appends the no-fake-pass judge persona to the
          diagnose system block;
        - a router routes the diagnosis path via router.route("diagnose")
          and a cheap-tier failure falls back to one strong retry (the
          router counts it);
        - a semantic cache serves cacheable diagnose prompts and skips the
          LLM round-trip on a hit;
        - a ToolCallSelfCheck forces the envelope output contract and runs
          the model round-trip through check_with_retry with the producer
          callable injected — an invalid envelope is never executed.

        Raises _LLMFixError for illegal output, BudgetExceeded for token
        overruns and LLMUnavailableError when no route exists — the caller
        converts each into an honest FAILED.
        """
        client = self.client
        if client is None:
            raise LLMUnavailableError("LLM 客户端未提供 (诊断-修复需要 --llm)")
        envelope_mode = self.tool_call_self_check is not None
        # The edit-proposal contract is the ONLY output contract of the
        # non-envelope diagnose call: the JSON Action Envelope tail is not
        # appended here anymore (it previously competed with the edits
        # schema and the model answered with {"action": ...} envelopes that
        # lacked the "edits" array — 首跑缺口 pallets__flask-4045).
        base = (
            SYSTEM_BLOCK + "\n\n" + TOOL_SCHEMA_BLOCK
            if envelope_mode
            else SYSTEM_BLOCK + "\n\n" + _EDIT_PROPOSAL_OUTPUT_BLOCK
        )
        if self.judge_persona:
            base = build_judge_prompt(base)
            self._judge_persona_applied += 1
        context = self._diagnose_context(
            step, result, diagnosis, envelope_mode=envelope_mode
        )
        if envelope_mode:
            return self._llm_fix_envelope(client, base, context, step, diagnosis)
        built = assemble(base, "diagnose", context, include_envelope=False)
        route = self.router.route("diagnose") if self.router is not None else None
        cached: dict[str, Any] | None = None
        cache_key_value = ""
        if self.semantic_cache is not None and cacheable("diagnose"):
            model = route.model if route is not None else ""
            cache_key_value = cache_key(
                _prompt_digest(built.text),
                model,
                {"step_id": step.id, "envelope": False},
            )
            hit = self.semantic_cache.get(cache_key_value)
            if isinstance(hit, dict) and isinstance(hit.get("ops"), list):
                cached = hit
        if cached is None:
            # EditProposalSelfCheck (ToolCallSelfCheck pattern): an invalid
            # or unparseable proposal arms exactly ONE deterministic repair
            # instruction; a second invalid proposal gives up carrying the
            # stable code LLM_PROPOSAL_INVALID.
            checker = EditProposalSelfCheck()

            def produce(instruction: str | None) -> object:
                text = (
                    built.text
                    if instruction is None
                    else f"{built.text}\n\n{instruction}"
                )
                response = self._diagnose_call(
                    client,
                    [LLMMessage(role="user", content=text)],
                    step,
                    text,
                    route,
                )
                content = response.content or ""
                try:
                    return extract_json_object(content)
                except (json.JSONDecodeError, TypeError, ValueError):
                    snippet = content.strip() or "(空输出)"
                    return ProposalParseFailure(snippet[-240:])

            outcome = checker.check_with_retry(produce)
            if outcome.status != "valid":
                raise _LLMFixError(
                    f"[{outcome.code}] LLM 编辑提案校验失败 "
                    f"(修复指令一次后仍失败): {outcome.message}"
                )
            data = checker.last_data
            if data is None:
                raise _LLMFixError(
                    f"[{CODE_PROPOSAL_INVALID}] 编辑提案校验通过但数据丢失 (程序错误)"
                )
            try:
                explanation, ops = _parse_edit_ops(data)
            except _LLMFixError as exc:
                raise _LLMFixError(
                    f"[{CODE_PROPOSAL_INVALID}] 编辑提案解析失败: {exc}"
                ) from exc
            if self.semantic_cache is not None and cache_key_value:
                self.semantic_cache.put(
                    cache_key_value,
                    {"explanation": explanation, "ops": ops},
                    kind="diagnose",
                )
        else:
            raw_explanation = cached.get("explanation")
            explanation = raw_explanation if isinstance(raw_explanation, str) else ""
            raw_ops = cached.get("ops")
            ops = raw_ops if isinstance(raw_ops, list) else []
        edited: list[str] = []
        for op in ops:
            action = op.get("action")
            path = op.get("path")
            new_value = op.get("new")
            if not isinstance(path, str) or not path.strip():
                raise _LLMFixError(f"编辑操作缺少合法 path: {op!r}")
            if action == "apply_edit":
                old_value = op.get("old")
                if not isinstance(old_value, str) or not isinstance(new_value, str):
                    raise _LLMFixError(f"apply_edit 需要字符串 old/new: {op!r}")
                if self.tool_registry is not None:
                    tool_result = self.tool_registry.dispatch(
                        self.tool_registry.build_tool_call(
                            "apply_patch",
                            {"path": path, "old": old_value, "new": new_value},
                        )
                    )
                    if tool_result.status != "ok":
                        raise _LLMFixError(f"apply_patch 被拒 ({path}): {tool_result.summary}")
                else:
                    try:
                        self.editor.apply_edit(path, old_value, new_value)
                    except EditError as exc:
                        raise _LLMFixError(f"apply_edit 被拒 ({path}): {exc}") from exc
            elif action == "write_file":
                if not isinstance(new_value, str):
                    raise _LLMFixError(f"write_file 需要字符串 new: {op!r}")
                if self.tool_registry is not None:
                    tool_result = self.tool_registry.dispatch(
                        self.tool_registry.build_tool_call(
                            "create_file", {"path": path, "content": new_value}
                        )
                    )
                    if tool_result.status != "ok":
                        raise _LLMFixError(f"create_file 被拒 ({path}): {tool_result.summary}")
                else:
                    try:
                        self.editor.write_file(path, new_value)
                    except EditError as exc:
                        raise _LLMFixError(f"write_file 被拒 ({path}): {exc}") from exc
            else:
                raise _LLMFixError(f"未知编辑动作 {action!r} (仅支持 apply_edit|write_file)")
            if path not in edited:
                edited.append(path)
        if explanation:
            return f"[LLM 诊断] {explanation}", edited
        return diagnosis, edited

    def _diagnose_call(
        self,
        client: LLMClient,
        messages: list[LLMMessage],
        step: Step,
        prompt_text: str,
        route: ProviderRoute | None,
    ) -> LLMResponse:
        """One diagnose chat round-trip; a cheap-tier failure falls back to
        exactly one strong retry, counted by the router (on_failure)."""

        def once() -> LLMResponse:
            response = client.chat_sync(
                messages,
                label=f"diagnose:{step.id}",
                kind="diagnose",
                job_id=self.job_id,
                step_id=step.id,
                thinking=resolve_craft_thinking("diagnose"),
                response_format={"type": "json_object"},
                estimated_prompt_tokens=max(1, len(prompt_text) // 4),
            )
            self.llm_calls += 1
            return response

        if route is None or route.tier != "cheap" or self.router is None:
            return once()
        try:
            return once()
        except LLMUnavailableError:
            self.router.on_failure(route)
            return once()

    def _llm_fix_envelope(
        self,
        client: LLMClient,
        base: str,
        context: dict[str, str],
        step: Step,
        diagnosis: str,
    ) -> tuple[str, list[str]]:
        """W44 self-checked envelope path: the model must answer with one
        JSON Action Envelope, validated through ToolCallSelfCheck
        .check_with_retry with the model round-trip injected as the
        producer callable. One retry is armed on an invalid envelope; a
        second invalid envelope gives up with the stable registry error
        code and the step fails with honest M1 semantics."""
        checker = self.tool_call_self_check
        registry = self.tool_registry
        if checker is None or registry is None:
            # Constructor validation makes this unreachable; kept for types.
            raise _LLMFixError("信封自检路径缺少 checker/registry (构造期应已拦截)")
        route = self.router.route("diagnose") if self.router is not None else None
        produced: list[object] = []

        def produce(instruction: str | None) -> object:
            sections = dict(context)
            if instruction:
                sections["self_check_repair"] = instruction
            built = assemble(base, "diagnose", sections, include_envelope=True)
            response = self._diagnose_call(
                client,
                [LLMMessage(role="user", content=built.text)],
                step,
                built.text,
                route,
            )
            try:
                payload = extract_json_object(response.content or "")
            except (json.JSONDecodeError, TypeError, ValueError):
                # The checker reports "not a JSON object" and arms its retry.
                payload = response.content
            produced.append(payload)
            return payload

        outcome = checker.check_with_retry(produce)
        if outcome.status != "valid":
            raise _LLMFixError(
                f"工具调用信封自检未通过 ({outcome.status}, code={outcome.code}): "
                f"{outcome.message}"
            )
        envelope = produced[-1]
        if not isinstance(envelope, dict):
            raise _LLMFixError("信封自检通过但载荷不是 JSON 对象 (内部不一致)")
        action = envelope.get("action")
        params = envelope.get("params")
        raw_version = envelope.get("version")
        if not isinstance(action, str) or not isinstance(params, dict):
            raise _LLMFixError("信封自检通过但 action/params 类型非法 (内部不一致)")
        if action not in ("apply_patch", "create_file"):
            raise _LLMFixError(
                f"信封自检通过但工具 {action!r} 不是编辑工具 "
                "(仅支持 apply_patch|create_file)"
            )
        version = (
            raw_version
            if isinstance(raw_version, int) and not isinstance(raw_version, bool)
            else None
        )
        tool_result = registry.dispatch(
            registry.build_tool_call(action, params, version=version)
        )
        if tool_result.status != "ok":
            raise _LLMFixError(f"{action} 被拒: {tool_result.summary}")
        path = params.get("path")
        if not isinstance(path, str) or not path.strip():
            raise _LLMFixError("信封缺少合法 path")
        return diagnosis, [path]

    def _diagnose_context(
        self,
        step: Step,
        result: ExecResult | None,
        diagnosis: str,
        *,
        envelope_mode: bool = False,
    ) -> dict[str, str]:
        """Failure context for the diagnose prompt: step schema, deterministic
        diagnosis, failure output tail, the current real content of each
        candidate source file as the edit anchor (first 400 lines, capped),
        the editor API contract and the JSON output contract. envelope_mode
        (W44 self-check) swaps the edit-proposal schema for the JSON Action
        Envelope contract."""
        # W113 anchor fix: the prompt must carry the CURRENT real content
        # of every candidate SOURCE file (bounded to the first 400 lines,
        # raw lines, no numbering) so the model quotes old strings from the
        # real text instead of reconstructing code from memory
        # (pallets__flask-4045: apply_edit 拒绝 old 未命中 src/flask/helpers.py).
        # Test files are excluded — editing them is forbidden and the hidden
        # tests are applied by the harness after craft.
        snippets: list[str] = []
        excluded_test_targets: list[str] = []
        for target in step.target_files[:8]:
            if is_test_file_path(target):
                excluded_test_targets.append(target)
                continue
            try:
                lines = self.editor.read_file(target, limit=401)
            except EditError:
                snippets.append(f"--- {target} ---\n<不可读>")
                continue
            over_line_limit = len(lines) > 400
            shown = lines[:400]
            text = "\n".join(line for _, line in shown)
            if len(text) > 12_000:
                cut = text.rfind("\n", 0, 12_000)
                if cut < 0:
                    cut = 12_000
                text = text[:cut] + "\n... (截断)"
            elif over_line_limit:
                text += "\n... (仅显示前 400 行)"
            snippets.append(f"--- {target} ---\n{text}")
        anchor_header = (
            "FILE CONTENT ANCHOR — quote old strings EXACTLY from the file content "
            "above: each candidate SOURCE file's current real text follows (at most "
            "the first 400 lines); every apply_edit \"old\" must be copied "
            "byte-for-byte from a real line above (indentation and inline whitespace "
            "included). Never reconstruct code from memory. Test files are excluded "
            "— hidden tests are applied by the harness itself after craft."
        )
        if excluded_test_targets:
            anchor_header += (
                f" Excluded test files: {sorted(excluded_test_targets)}."
            )
        target_section = (
            f"{anchor_header}\n\n" + "\n\n".join(snippets)
            if snippets
            else f"{anchor_header}\n\n(无候选源文件)"
        )
        if self.tool_registry is not None:
            tool_surface = wrap_data_section(self.tool_registry.envelope_block())
        else:
            tool_surface = _EDITOR_API_BLOCK
        return {
            "step": json.dumps(step.to_dict(), ensure_ascii=False, indent=2),
            "failure_diagnosis": diagnosis,
            "failure_output": (result.output_tail if result is not None else "") or "(无)",
            "forbidden_changes": "\n".join(self.spec.forbidden_changes) or "(无)",
            "target_files": target_section,
            "task_memory": self.memory.summarize_for_prompt() or "(无任务记忆)",
            "editor_api": tool_surface,
            "output_schema": (
                JSON_ACTION_ENVELOPE_BLOCK if envelope_mode else _EDIT_OPS_SCHEMA
            ),
        }

    @staticmethod
    def _error_signature(step: Step, result: ExecResult | None, note: str = "") -> str:
        if result is None:
            # 首跑缺口修复 (pallets__flask-4992): grep/read-only criteria run
            # no command at all, so there is no exec output to quote — the
            # real failure reason rides the note instead of a misleading
            # "<no-exec-output>" placeholder.
            core = note.strip()[:160] if note.strip() else "<no-exec-output>"
            return f"{step.id}|{core}"
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
            self._record_file_writes_from_audit(step_id)
            self.memory.add(
                "budget",
                f"tokens={round(self.client.budget.used if self.client else 0.0, 1)} "
                f"iterations={self.total_iterations} tool_calls={self.tool_calls_used}",
                step_id=step_id,
            )
            self.memory.save(self.artifact_dir)
        except CraftPlanError as exc:
            raise CraftLoopError(f"checkpoint 写入失败: {exc}") from exc
        except MemoryError as exc:
            raise CraftLoopError(f"memory 写入失败: {exc}") from exc
        self._store_set_progress(step_id, iteration)

    def _record_file_writes_from_audit(self, step_id: str) -> None:
        """file_written facts come from the editor audit (卷 XXI §21.1):
        write/edit/move/delete actions — the authoritative trail, not the
        fix functions' return values."""
        for entry in self.editor.audit:
            if entry.action in ("write", "edit"):
                self.memory.add("file_written", entry.path, step_id=step_id)
            elif entry.action == "delete":
                self.memory.add(
                    "file_written", f"deleted: {entry.path}", step_id=step_id
                )
            elif entry.action == "move":
                destination = entry.detail.removeprefix("→ ").strip()
                self.memory.add(
                    "file_written", f"{entry.path} -> {destination}", step_id=step_id
                )

    def interrupt_checkpoint(self) -> None:
        """Ctrl-C flush (卷 XXI §21.3): persist the in-flight step as an
        'interrupted' checkpoint entry plus memory.json, so craft resume
        continues after the last green step. Never writes report.json —
        that is a terminal artifact."""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        step_id = (
            self._current_step.id
            if self._current_step is not None
            else (self.last_green_step or "")
        )
        entry = {
            "job_id": self.job_id,
            "step_id": step_id,
            "iteration": 0,
            "diagnosis": "用户中断 (Ctrl-C), 当前步骤未完成",
            "edits_applied": [],
            "build_result": {"exit_code": -1, "failed_tests": [], "log_tail": ""},
            "verdict": "interrupted",
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
            self.memory.save(self.artifact_dir)
        except CraftPlanError as exc:
            raise CraftLoopError(f"中断落盘失败 (checkpoint): {exc}") from exc
        except MemoryError as exc:
            raise CraftLoopError(f"中断落盘失败 (memory): {exc}") from exc

    def _finish(self, result: str) -> dict[str, Any]:
        changed_files = sorted(
            {
                entry.path
                for entry in self.editor.audit
                if entry.action in ("write", "edit", "move", "delete")
            }
        )
        # Base snapshots for the Java contract checkers: the first Editor
        # backup per path is the original pre-craft content (audit order:
        # backup entry precedes its write/edit entry).
        base_files: dict[str, str] = {}
        for entry in self.editor.audit:
            if entry.action != "backup" or entry.path in base_files:
                continue
            backup_name = entry.detail.removeprefix("→ ").strip()
            backup_path = self.artifact_dir / "backup" / backup_name
            try:
                base_files[entry.path] = backup_path.read_text(encoding="utf-8")
            except OSError:
                continue
        if self.skip_self_verify:
            self_verify_report: dict[str, Any] = {
                "status": "skipped",
                "findings": [],
                "note": "--no-self-verify: 自校验被显式跳过 (report 诚实标注 skipped)",
            }
        else:
            try:
                self_verify_report = self_verify(
                    changed_files, self.workspace, base_files=base_files
                )
            except Exception as exc:
                # The gate must never lose the report: honest degradation.
                self_verify_report = {
                    "status": "skipped",
                    "findings": [],
                    "note": f"自校验执行异常, 诚实降级为 skipped: {exc!r}",
                }
        if self_verify_report["status"] == "failed":
            if result == "DONE":
                result = "FAILED"
                self_verify_report["note"] = (
                    str(self_verify_report.get("note"))
                    + "; 自校验硬门未通过: 终态 DONE 覆盖为 FAILED "
                    "(编辑不回滚, 现场保留供人工处置)"
                )
            else:
                self_verify_report["note"] = (
                    str(self_verify_report.get("note"))
                    + f"; 自校验硬门未通过, 但任务终态原为 {result} (非 DONE), 不改变终态"
                )
        # W35 gate composition: whenever the M3 self-verify gate actually ran,
        # run the full five-gate pipeline too and embed its summary. This is
        # informational here — the loop does NOT block on it beyond the
        # existing self-verify hard gate; craft/accept.py owns the full
        # closure (gates + SpecProof verification + certificate).
        gates_report: dict[str, Any] | None = None
        if not self.skip_self_verify:
            gates_report = self._run_gate_pipeline(
                changed_files, base_files, self_verify_report
            )
        self.memory.add(
            "decision",
            f"自校验: {self_verify_report['status']} "
            f"(findings={len(self_verify_report.get('findings') or [])})",
        )
        elapsed = self.now_fn() - self.started_at
        tokens_used = self.client.budget.used if self.client is not None else 0.0
        report: dict[str, Any] = {
            "job_id": self.job_id,
            "mode": self.plan.mode,
            "result": result,
            "steps": [state.to_dict() for state in self.states],
            "diff_stat": {"files_changed": len(changed_files), "files": changed_files},
            "self_verify": self_verify_report,
            "budget_used": {
                "tokens": round(tokens_used, 1),
                "iterations": self.total_iterations,
                "seconds": round(elapsed, 1),
            },
            "audit_trail": [entry.to_dict() for entry in self.editor.audit],
        }
        if gates_report is not None:
            report["gates"] = gates_report
        if self.client is not None:
            report["llm_usage"] = self.client.stats_report()
        if self.tool_registry is not None:
            report["tool_registry"] = {
                "present": True,
                "tools": self.tool_registry.tool_names(),
                "dispatches": self.tool_registry.dispatch_count,
            }
        # W44 gains: tool-call self-check counters (success rate included),
        # router fallbacks, cache hits and the judge-persona flag. Zeros
        # when nothing is configured — the report shape is stable.
        self_check_metrics: dict[str, Any] = (
            self.tool_call_self_check.metrics()
            if self.tool_call_self_check is not None
            else {}
        )
        report["gains"] = {
            "tool_call_attempts": int(self_check_metrics.get("attempts") or 0),
            "tool_call_valid": int(self_check_metrics.get("valid") or 0),
            "tool_call_retried": int(self_check_metrics.get("retried") or 0),
            "tool_call_success_rate": float(
                self_check_metrics.get("tool_call_success_rate") or 0.0
            ),
            "router_fallback_count": (
                int(self.router.fallback_count) if self.router is not None else 0
            ),
            "cache_hits": (
                int(self.semantic_cache.hits) if self.semantic_cache is not None else 0
            ),
            "judge_persona_applied": int(self._judge_persona_applied),
        }
        if self.plan.llm_fallback_reason:
            report["llm_fallback_reason"] = self.plan.llm_fallback_reason
        self.memory.add(
            "decision", f"任务终态: {result} (迭代 {self.total_iterations})"
        )
        self.memory.add(
            "budget",
            f"tokens={round(tokens_used, 1)} iterations={self.total_iterations} "
            f"tool_calls={self.tool_calls_used} seconds={round(elapsed, 1)}",
        )
        try:
            write_json_atomic(self.artifact_dir / "report.json", report)
            self.memory.save(self.artifact_dir)
        except CraftPlanError as exc:
            raise CraftLoopError(f"report 写入失败: {exc}") from exc
        except MemoryError as exc:
            raise CraftLoopError(f"memory 写入失败: {exc}") from exc
        # W35 terminal write: entering a terminal status releases the lease
        # automatically; a supervisor cancel that raced us wins (its
        # projection is final and is never overwritten).
        if self.store is not None:
            if result == "CANCELLED":
                report["job_store_note"] = (
                    "作业已被 supervisor 取消 (cancel 优先于租约), 不写终态投影"
                )
            else:
                mapped: JobStatus = "succeeded" if result == "DONE" else "failed"
                try:
                    self.store.update_status(self.job_id, mapped, result_json=report)
                except InvalidJobTransitionError:
                    report["job_store_note"] = (
                        "终态投影被 supervisor 覆盖 (cancel 优先), result_json 未更新"
                    )
        return report

    def _run_gate_pipeline(
        self,
        changed_files: list[str],
        base_files: dict[str, str],
        self_verify_report: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the five-gate pipeline at finish; gate 5 reuses the M3 report
        computed above (never re-scans), and any pipeline crash degrades to
        an honest error summary instead of losing the report."""
        def passthrough(
            changed: list[str],
            workspace: Path,
            base_files: Mapping[str, str] | None = None,
        ) -> dict[str, Any]:
            return self_verify_report

        try:
            pipeline = GatePipeline(
                self.workspace, executor=self.executor, self_verify_fn=passthrough
            )
            bundle = ChangeBundle(task_id=self.job_id, changed_files=list(changed_files))
            return pipeline.run(bundle, base_files=base_files).to_dict()
        except Exception as exc:
            return {
                "task_id": self.job_id,
                "overall": "error",
                "overall_note": f"门禁组合执行异常, 诚实降级 (不伪造结果): {exc!r}",
                "duration_ms": 0,
                "gates": [],
                "summary": (
                    f"GATES: task={self.job_id} overall=error duration_ms=0 "
                    f"(组合执行异常: {exc!r})"
                ),
            }

    @classmethod
    def from_checkpoint(
        cls,
        artifact_dir: str | Path,
        *,
        fix_registry: dict[str, FixFunction] | None = None,
        budget: Budget | None = None,
        exec_mode: str | None = None,
        exec_timeout: int = 600,
        python: str | None = None,
        client: LLMClient | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_call_self_check: ToolCallSelfCheck | None = None,
        router: ModelRouter | None = None,
        semantic_cache: SemanticCache | None = None,
        judge_persona: bool = False,
        store: AgentJobStore | None = None,
        lease_ttl_seconds: float = 900,
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
        try:
            memory = TaskMemory.load(directory)
        except MemoryError as exc:
            raise CraftLoopError(f"memory.json 损坏, 无法恢复 ({directory}): {exc}") from exc
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
            python=python,
            states=states,
            checkpoint_entries=entries,
            total_iterations=total_iterations,
            task_key=task_key,
            client=client,
            memory=memory,
            tool_registry=tool_registry,
            tool_call_self_check=tool_call_self_check,
            router=router,
            semantic_cache=semantic_cache,
            judge_persona=judge_persona,
            store=store,
            lease_ttl_seconds=lease_ttl_seconds,
        )
        loop.last_green_step = str(last_green)
        return loop
