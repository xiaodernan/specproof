"""Unified agent-facing schemas (商业化计划书 §4.2/§5.2/§6.2/§22-1).

Pydantic models shared by the orchestrator, the tool layer and the SpecProof
accept hand-off:

  AgentTask     — task envelope (task_id/text/repo/base_sha/execution_mode/
                  budget/desired_checks/network_policy/model_policy/idempotency_key)
  ToolCall      — versioned tool invocation (JSON Action Envelope)
  ToolResult    — structured tool result (untrusted data by contract)
  Approval      — approval request / record
  Artifact      — digest-addressed evidence artifact
  ChangeBundle  — delivery bundle for SpecProof accept (§4.6)
  PlanSchema / StepSchema — schema mirrors of the planner dataclasses with
                  bidirectional adapters (plan_to_schema / plan_from_schema /
                  step_to_schema / step_from_schema)

Versioning: every model carries schema_version=1 and REJECTS any other
version — the whole envelope upgrades together, never silently. Validation
is strict on every declared field; unknown keys are ignored (same
forward-compatibility policy as craft/spec.py).

DAG integrity reuses the planner's single source of truth: step ids must be
unique and deps must reference strictly earlier steps (no cycles) — the
schema can never describe a plan the M3 loop could not execute.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .budget import Budget
from .planner import (
    CRITERIA_TYPES,
    STEP_KINDS,
    Plan,
    Step,
    SuccessCriteria,
    _validate_step_dag,
    ensure_step_cap,
)
from .spec import TaskSpec

SCHEMA_VERSION = 1

EXECUTION_MODES: tuple[str, ...] = ("plan_only", "confirm_dangerous", "full_auto")
NETWORK_POLICIES: tuple[str, ...] = ("deny", "allowlisted", "allow")
MODEL_POLICIES: tuple[str, ...] = ("default", "fixed", "org_default")
APPROVAL_STATES: tuple[str, ...] = ("pending", "approved", "denied", "expired")
TOOL_RESULT_STATUSES: tuple[str, ...] = (
    "ok",
    "error",
    "denied",
    "cancelled",
    "timed_out",
)
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high", "critical")

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class SchemaError(ValueError):
    """A schema payload failed validation (pydantic ValidationError wraps it)."""


class SchemaModel(BaseModel):
    """Base for every agent-facing schema: pins schema_version."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = SCHEMA_VERSION

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: int) -> int:
        if value != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version 不受支持: {value} (当前版本 {SCHEMA_VERSION})"
            )
        return value


class AgentTask(SchemaModel):
    """Task envelope accepted by the orchestrator (计划书 §4.1/§5.2)."""

    task_id: str = Field(min_length=1)
    task_text: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    base_sha: str = ""
    execution_mode: Literal["plan_only", "confirm_dangerous", "full_auto"] = "plan_only"
    budget: dict[str, int] = Field(default_factory=dict)
    desired_checks: list[str] = Field(default_factory=list)
    network_policy: Literal["deny", "allowlisted", "allow"] = "deny"
    model_policy: Literal["default", "fixed", "org_default"] = "default"
    idempotency_key: str = ""

    @field_validator("budget")
    @classmethod
    def _check_budget(cls, value: dict[str, int]) -> dict[str, int]:
        for name, amount in value.items():
            if amount < 0:
                raise ValueError(f"budget[{name!r}] 不能为负数 (收到 {amount})")
        return value


class ToolCall(SchemaModel):
    """Versioned tool invocation (计划书 §6.2 JSON Action Envelope)."""

    tool: str = Field(min_length=1)
    version: int = Field(ge=1)
    call_id: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    budget_cost: dict[str, int] = Field(default_factory=dict)
    requires_approval: bool = False

    @field_validator("budget_cost")
    @classmethod
    def _check_budget_cost(cls, value: dict[str, int]) -> dict[str, int]:
        for name, amount in value.items():
            if amount < 0:
                raise ValueError(f"budget_cost[{name!r}] 不能为负数 (收到 {amount})")
        return value


class ToolResult(SchemaModel):
    """Structured tool result — untrusted data by contract (计划书 §6.2/§6.3).

    status carries the tool outcome; failure codes are NOT smuggled into it —
    they live as a stable [CODE] prefix in summary (see craft/tools.py).
    """

    status: Literal["ok", "error", "denied", "cancelled", "timed_out"] = "ok"
    exit_code: int | None = None
    summary: str = ""
    output_head: str = ""
    output_tail: str = ""
    truncated: bool = False
    artifact_refs: list[str] = Field(default_factory=list)
    duration: float = Field(default=0.0, ge=0.0)
    security_tags: list[str] = Field(default_factory=list)


class Approval(SchemaModel):
    """Approval request / record (计划书 §6.4). Expired approvals never
    carry over to a retried task."""

    action: str = Field(min_length=1)
    scope: str = ""
    impact: str = ""
    reason: str = ""
    risk: Literal["low", "medium", "high", "critical"] = "medium"
    alternatives: list[str] = Field(default_factory=list)
    state: Literal["pending", "approved", "denied", "expired"] = "pending"


class Artifact(SchemaModel):
    """Digest-addressed evidence artifact (计划书 §4.3/§4.6)."""

    kind: str = Field(min_length=1)
    digest: str
    ref: str
    size: int = Field(ge=0)

    @field_validator("digest")
    @classmethod
    def _check_digest(cls, value: str) -> str:
        if not _SHA256_HEX_RE.match(value):
            raise ValueError(f"digest 必须是 64 位 sha256 hex (收到 {value!r})")
        return value


class TestResult(SchemaModel):
    """One test invocation inside a ChangeBundle (计划书 §4.6)."""

    __test__ = False  # a pydantic model, never a pytest test class

    command: str = Field(min_length=1)
    exit_code: int
    summary: str = ""
    passed: bool


class ChangeBundle(SchemaModel):
    """Delivery bundle handed to SpecProof accept (计划书 §4.6)."""

    task_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1, default=1)
    changed_files: list[str] = Field(default_factory=list)
    diff: str = ""
    test_results: list[TestResult] = Field(default_factory=list)
    dependency_changes: list[str] = Field(default_factory=list)
    migration_notes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    rollback: str = ""
    specproof_result: dict[str, Any] | None = None


class SuccessCriteriaSchema(SchemaModel):
    """Mirror of planner.SuccessCriteria (mechanically decidable gates)."""

    type: str
    value: str = ""

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in CRITERIA_TYPES:
            raise ValueError(f"success_criteria.type 非法: {value!r} (仅 {CRITERIA_TYPES})")
        return value


class StepSchema(SchemaModel):
    """Mirror of planner.Step."""

    id: str = Field(min_length=1)
    kind: str
    target_files: list[str] = Field(default_factory=list)
    intent: str = ""
    success_criteria: SuccessCriteriaSchema
    deps: list[str] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        if value not in STEP_KINDS:
            raise ValueError(f"step.kind 非法: {value!r} (仅 {STEP_KINDS})")
        return value


class PlanSchema(SchemaModel):
    """Mirror of planner.Plan (计划书 §4.2 machine-executable DAG plan)."""

    task_title: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    steps: list[StepSchema] = Field(default_factory=list)
    risk_classification: dict[str, bool] = Field(default_factory=dict)
    budget_alloc: dict[str, int] = Field(default_factory=dict)
    llm_fallback_reason: str = ""


# -- adapters: schemas <-> planner dataclasses --------------------------------


def step_to_schema(step: Step) -> StepSchema:
    """planner.Step -> StepSchema (lossless)."""
    return StepSchema(
        id=step.id,
        kind=step.kind,
        target_files=list(step.target_files),
        intent=step.intent,
        success_criteria=SuccessCriteriaSchema(
            type=step.success_criteria.type, value=step.success_criteria.value
        ),
        deps=list(step.deps),
    )


def step_from_schema(schema: StepSchema) -> Step:
    """StepSchema -> planner.Step; invalid shape raises planner's errors."""
    return Step(
        id=schema.id,
        kind=schema.kind,
        target_files=list(schema.target_files),
        intent=schema.intent,
        success_criteria=SuccessCriteria(
            type=schema.success_criteria.type,  # type: ignore[arg-type]
            value=schema.success_criteria.value,
        ),
        deps=list(schema.deps),
    )


def plan_to_schema(plan: Plan) -> PlanSchema:
    """planner.Plan -> PlanSchema (lossless)."""
    return PlanSchema(
        task_title=plan.task_title,
        mode=plan.mode,
        steps=[step_to_schema(step) for step in plan.steps],
        risk_classification=dict(plan.risk_classification),
        budget_alloc=dict(plan.budget_alloc),
        llm_fallback_reason=plan.llm_fallback_reason,
    )


def plan_from_schema(schema: PlanSchema) -> Plan:
    """PlanSchema -> planner.Plan with the full M1/M2 hard gates: step cap +
    DAG validity (unique ids, deps reference strictly earlier steps)."""
    steps = [step_from_schema(item) for item in schema.steps]
    ensure_step_cap(steps)
    _validate_step_dag(steps)
    return Plan(
        task_title=schema.task_title,
        mode=schema.mode,
        steps=steps,
        risk_classification=dict(schema.risk_classification),
        budget_alloc=dict(schema.budget_alloc),
        llm_fallback_reason=schema.llm_fallback_reason,
    )


def agent_task_from_spec(
    spec: TaskSpec,
    *,
    task_id: str,
    repo: str,
    base_sha: str = "",
    execution_mode: str = "plan_only",
    budget: Budget | None = None,
    desired_checks: list[str] | None = None,
    network_policy: str = "deny",
    model_policy: str = "default",
    idempotency_key: str = "",
) -> AgentTask:
    """TaskSpec + task metadata -> AgentTask (计划书 §4.1 task normalization).

    task_text follows the deterministic parse_spec_text convention: the
    title is the first line, the remaining body lines join into the text.
    """
    if execution_mode not in EXECUTION_MODES:
        raise SchemaError(f"execution_mode 非法: {execution_mode!r} (仅 {EXECUTION_MODES})")
    if network_policy not in NETWORK_POLICIES:
        raise SchemaError(f"network_policy 非法: {network_policy!r} (仅 {NETWORK_POLICIES})")
    if model_policy not in MODEL_POLICIES:
        raise SchemaError(f"model_policy 非法: {model_policy!r} (仅 {MODEL_POLICIES})")
    body = [spec.title]
    if spec.description:
        body.append(spec.description)
    return AgentTask(
        task_id=task_id,
        task_text="\n".join(body),
        repo=repo,
        base_sha=base_sha,
        execution_mode=execution_mode,  # type: ignore[arg-type]
        budget=budget.to_dict() if budget is not None else {},
        desired_checks=list(desired_checks or []),
        network_policy=network_policy,  # type: ignore[arg-type]
        model_policy=model_policy,  # type: ignore[arg-type]
        idempotency_key=idempotency_key,
    )


def spec_from_agent_task(task: AgentTask) -> TaskSpec:
    """AgentTask -> TaskSpec (title = first line, description = the rest).

    desired_checks become acceptance criteria verbatim — they name the gates
    the task must pass, which is exactly what acceptance criteria express.
    """
    lines = task.task_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body = [line for line in lines if line.strip()]
    if not body:
        raise SchemaError("agent_task.task_text 为空: 无法提取 title/description")
    return TaskSpec(
        title=body[0],
        description="\n".join(body[1:]),
        acceptance_criteria=list(task.desired_checks),
        forbidden_changes=[],
        affected_area_hint="",
    )


def sha256_hex(data: bytes) -> str:
    """sha256 hexdigest — the canonical digest format for Artifact/editor."""
    return hashlib.sha256(data).hexdigest()


def valid_digest(value: str) -> bool:
    """True when value is a well-formed sha256 hex digest."""
    return bool(_SHA256_HEX_RE.match(value))


__all__ = [
    "APPROVAL_STATES",
    "EXECUTION_MODES",
    "MODEL_POLICIES",
    "NETWORK_POLICIES",
    "RISK_LEVELS",
    "SCHEMA_VERSION",
    "TOOL_RESULT_STATUSES",
    "AgentTask",
    "Approval",
    "Artifact",
    "ChangeBundle",
    "PlanSchema",
    "SchemaError",
    "SchemaModel",
    "StepSchema",
    "SuccessCriteriaSchema",
    "TestResult",
    "ToolCall",
    "ToolResult",
    "agent_task_from_spec",
    "plan_from_schema",
    "plan_to_schema",
    "sha256_hex",
    "spec_from_agent_task",
    "step_from_schema",
    "step_to_schema",
    "valid_digest",
]
