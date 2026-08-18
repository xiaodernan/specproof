"""M1 plan generation (design doc §4.2): deterministic rule engine.

Task keywords -> step template (understand -> modify/add -> test -> verify),
each step carrying kind / target_files / intent / mechanically decidable
success_criteria (compile | test_green | grep). Step count capped at 12.

LLM enrichment is M2: the interface signature exists, but M1 either degrades
to the rule plan (mode="llm" request, per §9) or raises an explicit error
(compile_plan_llm) — it never pretends a model was called. Plans carry
mode="deterministic".
"""

from __future__ import annotations

import json
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .budget import Budget
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_title": self.task_title,
            "mode": self.mode,
            "steps": [step.to_dict() for step in self.steps],
            "risk_classification": dict(self.risk_classification),
            "budget_alloc": dict(self.budget_alloc),
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
        return cls(
            task_title=title,
            mode=mode,
            steps=steps,
            risk_classification={str(k): v for k, v in risk.items()},
            budget_alloc={str(k): v for k, v in budget.items()},
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


def compile_plan(
    spec: TaskSpec, *, mode: str = "deterministic", budget: Budget | None = None
) -> Plan:
    """Deterministic rule-engine plan. mode="llm" degrades to the rule plan
    and is honestly labelled mode="deterministic" (§9) — no model is called."""
    if mode not in ("deterministic", "llm"):
        raise CraftModeError(f"不支持的计划模式: {mode!r} (M1: deterministic)")
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
    text = " ".join([spec.title, spec.description, *spec.acceptance_criteria]).lower()
    risk = {
        flag: flag in template.risk_flags
        or any(keyword in text for keyword in _RISK_KEYWORDS[flag])
        for flag in _RISK_FLAG_NAMES
    }
    return Plan(
        task_title=spec.title,
        mode="deterministic",
        steps=steps,
        risk_classification=risk,
        budget_alloc={
            "iterations": active_budget.max_iterations,
            "tokens": active_budget.token_budget,
        },
    )


def compile_plan_llm(spec: TaskSpec, *, provider: object | None = None) -> Plan:
    """LLM-enriched planning entry — M2 scope. M1 keeps the signature but
    refuses loudly instead of pretending a model call happened."""
    raise CraftModeError(
        "LLM 规划尚未接线 (M2 范围): M1 请使用 compile_plan (deterministic) / --no-llm"
    )
