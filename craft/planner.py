"""M1 rule engine + M2 LLM planning (design doc §4.2).

Deterministic path: task keywords -> step template (understand ->
modify/add -> test -> verify), each step carrying kind / target_files /
intent / mechanically decidable success_criteria (compile | test_green |
grep). Step count capped at 12.

LLM path (M2): compile_plan(mode="llm") / compile_plan_llm() call the
model through craft.llm.LLMClient with the cache-friendly
prompt_templates.assemble() prefix and a JSON output contract. Success ->
Plan(mode="llm"). ANY failure (no key, probe failure, budget overrun,
unparseable or schema-invalid output, step cap or dependency-cycle
violation) degrades to the deterministic rule plan with the reason on
llm_fallback_reason — it never raises and never pretends a model was
called when it was not.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from providers.base import LLMMessage, ModelProvider
from providers.budget import BudgetExceeded
from providers.prompt_templates import SYSTEM_BLOCK, TOOL_SCHEMA_BLOCK, assemble

from .budget import Budget
from .editor import sha256_digest
from .llm import LLMClient, LLMUnavailableError, extract_json_object, resolve_craft_thinking
from .spec import TaskSpec

CRITERIA_TYPES: tuple[str, ...] = ("compile", "test_green", "grep")
STEP_KINDS: tuple[str, ...] = ("understand", "modify", "add", "test", "verify")
MAX_PLAN_STEPS = 12


class CraftPlanError(ValueError):
    """Plan construction or deserialization failed validation."""


class PlanTooComplexError(CraftPlanError):
    """Step count exceeds MAX_PLAN_STEPS."""


class CraftModeError(RuntimeError):
    """Requested craft mode is not wired in M1."""


@dataclass(frozen=True)
class SuccessCriteria:
    """Mechanically decidable step gate (design §4.2 hard constraint)."""

    type: Literal["compile", "test_green", "grep"]
    value: str = ""

    def __post_init__(self) -> None:
        if self.type not in CRITERIA_TYPES:
            raise CraftPlanError(f"success_criteria.type 非法: {self.type!r}")

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SuccessCriteria:
        kind = data.get("type")
        value = data.get("value", "")
        if not isinstance(kind, str) or kind not in CRITERIA_TYPES:
            raise CraftPlanError(f"success_criteria.type 非法: {kind!r}")
        if not isinstance(value, str):
            raise CraftPlanError("success_criteria.value 类型错误: 应为字符串")
        return cls(type=kind, value=value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Step:
    id: str
    kind: str
    target_files: list[str] = field(default_factory=list)
    intent: str = ""
    success_criteria: SuccessCriteria = field(default_factory=lambda: SuccessCriteria("grep"))
    deps: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise CraftPlanError("step.id 不能为空")
        if self.kind not in STEP_KINDS:
            raise CraftPlanError(f"step.kind 非法: {self.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "target_files": list(self.target_files),
            "intent": self.intent,
            "success_criteria": self.success_criteria.to_dict(),
            "deps": list(self.deps),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        step_id = data.get("id")
        kind = data.get("kind")
        if not isinstance(step_id, str) or not step_id.strip():
            raise CraftPlanError("step.id 缺失或为空")
        if not isinstance(kind, str) or kind not in STEP_KINDS:
            raise CraftPlanError(f"step.kind 非法: {kind!r}")
        targets = data.get("target_files", [])
        if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
            raise CraftPlanError(f"step {step_id} 的 target_files 应为字符串数组")
        intent = data.get("intent", "")
        deps = data.get("deps", [])
        if not isinstance(intent, str) or not isinstance(deps, list):
            raise CraftPlanError(f"step {step_id} 的 intent/deps 类型错误")
        criteria = data.get("success_criteria")
        if not isinstance(criteria, dict):
            raise CraftPlanError(f"step {step_id} 缺少 success_criteria")
        return cls(
            id=step_id,
            kind=kind,
            target_files=list(targets),
            intent=intent,
            success_criteria=SuccessCriteria.from_dict(criteria),
            deps=list(deps),
        )


_INTENTS: dict[str, str] = {
    "understand": "阅读目标代码与既有约定 (M1 仅做可读性检查, 不注入上下文)",
    "modify": "按任务修改实现代码",
    "add": "新增实现/测试代码",
    "test": "运行测试套件并保证全绿",
    "verify": "机械核验变更已落地且测试全绿",
}


@dataclass(frozen=True)
class _TaskTemplate:
    key: str
    label: str
    step_kinds: tuple[str, ...]
    risk_flags: tuple[str, ...] = ()


_TEMPLATES: dict[str, _TaskTemplate] = {
    "add_endpoint": _TaskTemplate(
        "add_endpoint", "新增端点", ("understand", "add", "test", "verify"), ("auth", "public_api")
    ),
    "add_test": _TaskTemplate(
        "add_test", "新增测试", ("understand", "add", "test", "verify"), ()
    ),
    "migration": _TaskTemplate(
        "migration", "数据迁移", ("understand", "modify", "test", "verify"), ("migration",)
    ),
    "cache": _TaskTemplate(
        "cache", "引入缓存", ("understand", "add", "test", "verify"), ()
    ),
    "refactor": _TaskTemplate(
        "refactor", "等价重构", ("understand", "modify", "test", "verify"), ()
    ),
    "fix_bug": _TaskTemplate(
        "fix_bug", "修复缺陷", ("understand", "modify", "test", "verify"), ()
    ),
    "generic": _TaskTemplate(
        "generic", "通用任务", ("understand", "modify", "test", "verify"), ()
    ),
}

# Ordered keyword rules: the first matching rule wins (deterministic).
_TASK_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("add_endpoint", ("端点", "endpoint", "接口", " rest ", " api ")),
    ("add_test", ("加测试", "补测试", "新增测试", "add test", "写测试", "junit")),
    ("migration", ("迁移", "migrat")),
    ("cache", ("缓存", "cache", " redis")),
    ("refactor", ("重构", "refactor")),
    ("fix_bug", ("修复", "修 bug", "bug", "缺陷", "逻辑", "错误", "fix")),
)

_RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "auth": ("auth", "鉴权", "授权", "权限", "preauthorize", "登录", "认证"),
    "migration": ("迁移", "migrat", "schema"),
    "mq": ("mq", "rabbit", "kafka", "消息队列", "消息", "publish", "订阅"),
    "public_api": ("api", "接口", "端点", "endpoint", "公开", "rest"),
}

_RISK_FLAG_NAMES: tuple[str, ...] = ("auth", "migration", "mq", "public_api")


def classify_task(spec: TaskSpec) -> str:
    """Deterministic keyword classification -> template key."""
    text = " ".join([spec.title, spec.description, *spec.acceptance_criteria]).lower()
    for key, keywords in _TASK_RULES:
        if any(keyword in text for keyword in keywords):
            return key
    return "generic"


def _derive_target_files(affected_area_hint: str) -> list[str]:
    """Hint tokens (split on commas/spaces) are treated as concrete target
    files only when they look like file names (contain a dot); area words
    like controller/service/repository are reserved for M5 context retrieval
    and yield no concrete targets."""
    tokens = [t.strip() for t in re.split(r"[,\s，、]+", affected_area_hint) if t.strip()]
    return [t for t in tokens if "." in t]


def _extract_path_like(spec: TaskSpec) -> str:
    text = " ".join([spec.title, spec.description, *spec.acceptance_criteria])
    match = re.search(r"(/[A-Za-z0-9{}_.:?=&/@%+-]{2,})", text)
    return match.group(1) if match else ""


def _criteria_for(
    kind: str, template_key: str, spec: TaskSpec, target_files: list[str]
) -> SuccessCriteria:
    if kind == "understand":
        # value="" means a readability check over target_files in the loop.
        return SuccessCriteria("grep", "")
    if kind in ("modify", "add"):
        return SuccessCriteria("compile", "")
    if kind == "test":
        return SuccessCriteria("test_green", "")
    # kind == "verify"
    if template_key == "add_endpoint" and target_files:
        path = _extract_path_like(spec)
        if path:
            return SuccessCriteria("grep", path)
    return SuccessCriteria("test_green", "")


def ensure_step_cap(steps: list[Step]) -> list[Step]:
    """Hard cap from design §4.2: a plan may never exceed 12 steps."""
    if len(steps) > MAX_PLAN_STEPS:
        raise PlanTooComplexError(
            f"计划步骤数 {len(steps)} 超过上限 {MAX_PLAN_STEPS}"
        )
    return steps


@dataclass(frozen=True)
class Plan:
    task_title: str
    mode: str
    steps: list[Step]
    risk_classification: dict[str, bool]
    budget_alloc: dict[str, int]
    # M2: set when an llm-mode request degraded to the rule plan. It is the
    # honest on-record reason (e.g. "LLM unavailable", "LLM 计划解析失败").
    llm_fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_title": self.task_title,
            "mode": self.mode,
            "steps": [step.to_dict() for step in self.steps],
            "risk_classification": dict(self.risk_classification),
            "budget_alloc": dict(self.budget_alloc),
            "llm_fallback_reason": self.llm_fallback_reason,
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target, self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        title = data.get("task_title")
        mode = data.get("mode")
        if not isinstance(title, str) or not title.strip():
            raise CraftPlanError("plan.task_title 缺失或为空")
        if not isinstance(mode, str):
            raise CraftPlanError("plan.mode 类型错误: 应为字符串")
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list) or not all(isinstance(s, dict) for s in raw_steps):
            raise CraftPlanError("plan.steps 应为步骤对象数组")
        steps = ensure_step_cap([Step.from_dict(s) for s in raw_steps])
        risk = data.get("risk_classification", {})
        if not isinstance(risk, dict) or not all(isinstance(v, bool) for v in risk.values()):
            raise CraftPlanError("plan.risk_classification 应为 {str: bool}")
        budget = data.get("budget_alloc", {})
        if not isinstance(budget, dict) or not all(
            isinstance(k, str) and isinstance(v, int) for k, v in budget.items()
        ):
            raise CraftPlanError("plan.budget_alloc 应为 {str: int}")
        fallback = data.get("llm_fallback_reason", "")
        if not isinstance(fallback, str):
            raise CraftPlanError("plan.llm_fallback_reason 类型错误: 应为字符串")
        return cls(
            task_title=title,
            mode=mode,
            steps=steps,
            risk_classification={str(k): v for k, v in risk.items()},
            budget_alloc={str(k): v for k, v in budget.items()},
            llm_fallback_reason=fallback,
        )


def write_json_atomic(path: Path, payload: object) -> None:
    """JSON artifact writer: temp file + os.replace, LF, never half-written."""
    tmp = path.parent / f".{path.name}.{_tmp_suffix()}.tmp"
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        with suppress(OSError):
            tmp.unlink()
        raise CraftPlanError(f"写入产物失败 ({path}): {exc}") from exc


def _tmp_suffix() -> str:
    import secrets

    return secrets.token_hex(6)


_PLAN_OUTPUT_SCHEMA: str = """\
OUTPUT CONTRACT — respond with exactly one JSON object. No markdown fences,
no prose around the JSON. The JSON must match this schema:

{
  "steps": [
    {
      "id": "s1",
      "kind": "understand | modify | add | test | verify",
      "target_files": ["calc.py"],
      "intent": "one sentence: what this step does and why",
      "success_criteria": {"type": "compile | test_green | grep", "value": ""},
      "deps": []
    }
  ],
  "risk_classification": {"auth": false, "migration": false, "mq": false, "public_api": false}
}

Hard constraints (violating any of them invalidates the whole plan):
- at most 12 steps; step ids must be unique;
- deps may only reference strictly earlier step ids — no cycles;
- every success_criteria.type must be one of compile | test_green | grep
  (mechanically decidable); value stays "" for compile/test_green, and for
  grep it is the literal that must appear in every target_file;
- target_files are repo-relative paths; list only files this step really
  needs to read or change; never invent code contents.
"""


def compile_plan(
    spec: TaskSpec,
    *,
    mode: str = "deterministic",
    budget: Budget | None = None,
    client: LLMClient | None = None,
) -> Plan:
    """Plan entry: deterministic rule engine (M1) or real LLM planning (M2).

    mode="llm" calls the model through LLMClient; any failure (no key,
    probe failure, budget overrun, unparseable/invalid output) degrades to
    the rule plan with the reason on llm_fallback_reason — never an
    exception, never a fabricated model plan.
    """
    if mode not in ("deterministic", "llm"):
        raise CraftModeError(f"不支持的计划模式: {mode!r} (deterministic | llm)")
    if mode == "llm":
        return compile_plan_llm(spec, budget=budget, client=client)
    return _build_deterministic(spec, budget)


def _build_deterministic(spec: TaskSpec, budget: Budget | None) -> Plan:
    """M1 rule engine: template steps -> risk flags -> budget allocation."""
    active_budget = budget or Budget.from_env()
    template = _TEMPLATES[classify_task(spec)]
    target_files = _derive_target_files(spec.affected_area_hint)
    steps: list[Step] = []
    for index, kind in enumerate(template.step_kinds, start=1):
        steps.append(
            Step(
                id=f"s{index}",
                kind=kind,
                target_files=list(target_files) if kind in ("understand", "modify", "add") else [],
                intent=_INTENTS[kind],
                success_criteria=_criteria_for(kind, template.key, spec, target_files),
            )
        )
    ensure_step_cap(steps)
    return Plan(
        task_title=spec.title,
        mode="deterministic",
        steps=steps,
        risk_classification=_risk_flags_for(spec),
        budget_alloc={
            "iterations": active_budget.max_iterations,
            "tokens": active_budget.token_budget,
        },
    )


def _risk_flags_for(spec: TaskSpec) -> dict[str, bool]:
    template = _TEMPLATES[classify_task(spec)]
    text = " ".join([spec.title, spec.description, *spec.acceptance_criteria]).lower()
    return {
        flag: flag in template.risk_flags
        or any(keyword in text for keyword in _RISK_KEYWORDS[flag])
        for flag in _RISK_FLAG_NAMES
    }


def compile_plan_llm(
    spec: TaskSpec,
    *,
    provider: ModelProvider | None = None,
    client: LLMClient | None = None,
    budget: Budget | None = None,
) -> Plan:
    """M2: real LLM planning with honest degradation.

    Success -> Plan(mode="llm"). Any failure (no key, probe failure,
    budget overrun, unparseable or schema-invalid output, step cap or
    dependency-cycle violation) -> the deterministic rule plan carrying
    the reason on llm_fallback_reason. No exception escapes; nothing is
    faked.
    """
    active_budget = budget or Budget.from_env()
    llm = client or LLMClient(provider=provider)
    if not llm.available:
        return _llm_fallback(
            spec, active_budget, "LLM unavailable: " + llm.unavailable_reason()
        )
    try:
        built = assemble(
            SYSTEM_BLOCK + "\n\n" + TOOL_SCHEMA_BLOCK,
            "plan",
            {
                "task_spec": json.dumps(spec.to_dict(), ensure_ascii=False, indent=2),
                "output_schema": _PLAN_OUTPUT_SCHEMA,
            },
        )
        response = llm.chat_sync(
            [LLMMessage(role="user", content=built.text)],
            label="plan",
            kind="draft",
            step_id="plan",
            thinking=resolve_craft_thinking("plan"),
            response_format={"type": "json_object"},
            estimated_prompt_tokens=max(1, len(built.text) // 4),
        )
        data = extract_json_object(response.content or "")
        return _llm_plan_from_data(spec, data, active_budget)
    except BudgetExceeded as exc:
        return _llm_fallback(spec, active_budget, f"LLM 规划超 token 预算: {exc}")
    except LLMUnavailableError as exc:
        return _llm_fallback(spec, active_budget, "LLM unavailable: " + str(exc))
    except (CraftPlanError, json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
        return _llm_fallback(spec, active_budget, f"LLM 计划解析/校验失败: {exc}")
    except Exception as exc:
        return _llm_fallback(
            spec, active_budget, f"LLM 规划调用失败: {type(exc).__name__}: {exc}"
        )


def _llm_plan_from_data(spec: TaskSpec, data: object, budget: Budget) -> Plan:
    """Validate model output through the M1 Plan/Step schema + M2 DAG rules."""
    if not isinstance(data, dict):
        raise CraftPlanError("LLM 计划输出顶层必须是 JSON 对象")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not all(isinstance(s, dict) for s in raw_steps):
        raise CraftPlanError("LLM 计划缺少 steps 数组 (每个元素为对象)")
    steps = [Step.from_dict(s) for s in raw_steps]
    ensure_step_cap(steps)
    _validate_step_dag(steps)
    risk = _risk_flags_for(spec)
    raw_risk = data.get("risk_classification")
    if isinstance(raw_risk, dict) and all(
        isinstance(key, str) and isinstance(value, bool) for key, value in raw_risk.items()
    ):
        risk = {str(key): value for key, value in raw_risk.items()}
    budget_alloc = {
        "iterations": budget.max_iterations,
        "tokens": budget.token_budget,
    }
    raw_alloc = data.get("budget_alloc")
    if isinstance(raw_alloc, dict) and all(
        isinstance(key, str) and isinstance(value, int) for key, value in raw_alloc.items()
    ):
        budget_alloc = {str(key): value for key, value in raw_alloc.items()}
    return Plan(
        task_title=spec.title,
        mode="llm",
        steps=steps,
        risk_classification=risk,
        budget_alloc=budget_alloc,
    )


def _validate_step_dag(steps: list[Step]) -> list[Step]:
    """M2 hard constraint (design §4.2): unique ids, deps reference
    strictly earlier steps, no cycles."""
    ids = [step.id for step in steps]
    if len(set(ids)) != len(ids):
        raise CraftPlanError("LLM 计划存在重复 step.id")
    order = {step_id: index for index, step_id in enumerate(ids)}
    for step in steps:
        for dep in step.deps:
            if dep not in order:
                raise CraftPlanError(f"step {step.id} 的依赖 {dep!r} 不存在")
            if order[dep] >= order[step.id]:
                raise CraftPlanError(
                    f"step {step.id} 的依赖 {dep!r} 次序非法 (必须引用更早步骤, 无循环)"
                )
    return steps


def _llm_fallback(spec: TaskSpec, budget: Budget, reason: str) -> Plan:
    """Degrade to the M1 rule plan with the honest reason on record."""
    plan = _build_deterministic(spec, budget)
    return replace(plan, llm_fallback_reason=reason)

# -- plan versioning (计划书 §5.3) --------------------------------------------
#
# Plan revisions must be versioned: when the model changes a plan mid-run, the
# system records the old plan, the new plan, the reason, who approved and the
# budget delta — a model must never be able to rewrite its own plan to bypass
# the original approval. This section is purely additive: the execution loop's
# plan handling is untouched; the loop wiring persists PlanVersion records and
# consults plan_change_requires_approval before accepting a revision.

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PlanVersion:
    """One recorded plan revision (计划书 §5.3: 计划变更必须版本化).

    base_plan_digest is the sha256 of the canonical serialization
    (plan_digest) of the plan this revision replaces; version numbers are
    assigned by the caller, which owns the per-plan counter and the
    persisted revision history.
    """

    plan_id: str
    version: int
    base_plan_digest: str
    reason: str
    approved_by: str
    budget_delta: dict[str, int] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise CraftPlanError("PlanVersion.plan_id 不能为空")
        if self.version < 1:
            raise CraftPlanError(f"PlanVersion.version 必须 >= 1 (收到 {self.version})")
        if not _SHA256_HEX_RE.fullmatch(self.base_plan_digest):
            raise CraftPlanError(
                f"PlanVersion.base_plan_digest 必须是 64 位 sha256 hex "
                f"(收到 {self.base_plan_digest!r})"
            )
        if not all(isinstance(value, int) for value in self.budget_delta.values()):
            raise CraftPlanError("PlanVersion.budget_delta 应为 {str: int}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "version": self.version,
            "base_plan_digest": self.base_plan_digest,
            "reason": self.reason,
            "approved_by": self.approved_by,
            "budget_delta": dict(self.budget_delta),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanVersion:
        plan_id = data.get("plan_id")
        version = data.get("version")
        digest = data.get("base_plan_digest")
        reason = data.get("reason")
        approved_by = data.get("approved_by")
        delta = data.get("budget_delta", {})
        created_at = data.get("created_at", "")
        if not isinstance(plan_id, str) or not plan_id.strip():
            raise CraftPlanError("PlanVersion.plan_id 缺失或为空")
        if not isinstance(version, int) or isinstance(version, bool):
            raise CraftPlanError("PlanVersion.version 类型错误: 应为整数")
        if not isinstance(digest, str):
            raise CraftPlanError("PlanVersion.base_plan_digest 类型错误: 应为字符串")
        if not isinstance(reason, str) or not isinstance(approved_by, str):
            raise CraftPlanError("PlanVersion.reason/approved_by 类型错误: 应为字符串")
        if not isinstance(created_at, str):
            raise CraftPlanError("PlanVersion.created_at 类型错误: 应为字符串")
        if not isinstance(delta, dict) or not all(
            isinstance(key, str) and isinstance(value, int) for key, value in delta.items()
        ):
            raise CraftPlanError("PlanVersion.budget_delta 应为 {str: int}")
        return cls(
            plan_id=plan_id,
            version=version,
            base_plan_digest=digest,
            reason=reason,
            approved_by=approved_by,
            budget_delta={str(key): value for key, value in delta.items()},
            created_at=created_at,
        )


def plan_digest(plan: Plan) -> str:
    """sha256 hex of the canonical plan serialization (计划书 §5.3).

    Canonical form: Plan.to_dict() -> json.dumps(sort_keys=True,
    ensure_ascii=False, compact separators) -> UTF-8 bytes -> sha256. Equal
    content always digests equal regardless of dict key order; any content
    change — a reordered step list included — changes the digest. Reuses
    craft.editor.sha256_digest, the project-wide digest convention
    (craft/schemas.py's helper is unavailable here: schemas imports planner).
    """
    canonical = json.dumps(
        plan.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return sha256_digest(canonical.encode("utf-8"))


def record_plan_change(
    old_plan: Plan,
    new_plan: Plan,
    reason: str,
    budget_delta: dict[str, int] | None = None,
    *,
    plan_id: str | None = None,
    version: int = 1,
    approved_by: str = "",
    created_at: str | None = None,
) -> PlanVersion:
    """Record one plan revision with the same hard gates the loop enforces.

    The new plan must satisfy step cap + DAG validity (unique ids, deps
    reference strictly earlier steps, no cycles) — a violation raises
    CraftPlanError and nothing is recorded. base_plan_digest freezes the
    exact old plan this revision replaces.

    plan_id defaults to f"{old_plan.mode}:{old_plan.task_title}" (the plan
    lineage of the revised task); callers with a job/task id may override
    it. version is caller-assigned (the wiring owns the counter and the
    persisted history). budget_delta=None derives per-key
    new_plan.budget_alloc - old_plan.budget_alloc, keeping only non-zero
    entries. created_at=None stamps the current UTC time.
    """
    ensure_step_cap(new_plan.steps)
    _validate_step_dag(new_plan.steps)
    delta = budget_delta
    if delta is None:
        keys = sorted(set(old_plan.budget_alloc) | set(new_plan.budget_alloc))
        derived = {
            key: new_plan.budget_alloc.get(key, 0) - old_plan.budget_alloc.get(key, 0)
            for key in keys
        }
        delta = {key: value for key, value in derived.items() if value != 0}
    elif not all(isinstance(value, int) for value in delta.values()):
        raise CraftPlanError("budget_delta 应为 {str: int}")
    return PlanVersion(
        plan_id=plan_id or f"{old_plan.mode}:{old_plan.task_title}",
        version=version,
        base_plan_digest=plan_digest(old_plan),
        reason=reason,
        approved_by=approved_by,
        budget_delta=dict(delta),
        created_at=created_at or datetime.now(UTC).isoformat(timespec="seconds"),
    )


def plan_change_requires_approval(old_plan: Plan, new_plan: Plan) -> bool:
    """True when a plan revision is material enough to need approval (计划书 §5.3).

    Approval is required when the new plan
      - adds steps (any step id absent from the old plan);
      - extends scope to paths outside the old plan's owned paths (any
        target_files entry the old plan did not own — M1's owned-path
        contract, enforced at craft/tools.py);
      - changes its risk/approval flags in EITHER direction
        (risk_classification is the plan's approval indicator: adding a flag
        raises risk, removing one would dodge the original approval — the
        anti-bypass rule of §5.3);
      - raises the budget (any budget_alloc key with a larger value).
    Cosmetic revisions — step reorder, intent/annotation text, narrowing
    paths, lowering budget — need no approval.
    """
    if _added_step_ids(old_plan, new_plan):
        return True
    if _new_target_paths(old_plan, new_plan):
        return True
    if old_plan.risk_classification != new_plan.risk_classification:
        return True
    return _budget_raised(old_plan, new_plan)


def _added_step_ids(old_plan: Plan, new_plan: Plan) -> bool:
    """Any new step id not present in the old plan counts as adding a step."""
    return bool(
        {step.id for step in new_plan.steps} - {step.id for step in old_plan.steps}
    )


def _new_target_paths(old_plan: Plan, new_plan: Plan) -> bool:
    """Any path the new plan targets that the old plan did not own."""
    old_paths = {path for step in old_plan.steps for path in step.target_files}
    new_paths = {path for step in new_plan.steps for path in step.target_files}
    return bool(new_paths - old_paths)


def _budget_raised(old_plan: Plan, new_plan: Plan) -> bool:
    """Any budget_alloc key whose value grew from old to new."""
    keys = set(old_plan.budget_alloc) | set(new_plan.budget_alloc)
    return any(
        new_plan.budget_alloc.get(key, 0) > old_plan.budget_alloc.get(key, 0)
        for key in keys
    )

