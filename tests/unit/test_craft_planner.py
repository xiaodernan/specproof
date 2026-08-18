"""craft/planner.py unit tests — determinism, templates, caps, serialization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from craft.budget import Budget
from craft.planner import (
    MAX_PLAN_STEPS,
    CraftModeError,
    CraftPlanError,
    Plan,
    PlanTooComplexError,
    Step,
    SuccessCriteria,
    compile_plan,
    compile_plan_llm,
    ensure_step_cap,
)
from craft.spec import TaskSpec


def make_spec(
    title: str = "任务",
    description: str = "",
    criteria: tuple[str, ...] = (),
    hint: str = "",
) -> TaskSpec:
    return TaskSpec(
        title=title,
        description=description,
        acceptance_criteria=list(criteria),
        affected_area_hint=hint,
    )


def test_plan_is_deterministic_same_input_same_plan() -> None:
    spec = make_spec(
        title="给 UserService 加按邮箱查询的 REST 端点",
        description="增加 GET /users/by-email 支持分页与缓存",
        criteria=("200 返回", "未知邮箱 404"),
        hint="controller/service/repository",
    )
    assert compile_plan(spec).to_dict() == compile_plan(spec).to_dict()


def test_plan_mode_is_deterministic() -> None:
    assert compile_plan(make_spec()).mode == "deterministic"


def test_llm_mode_degrades_to_rule_plan_with_honest_label() -> None:
    plan = compile_plan(make_spec(), mode="llm")
    assert plan.mode == "deterministic"  # §9 降级, 不假装调模型


def test_compile_plan_llm_interface_refuses_loudly() -> None:
    with pytest.raises(CraftModeError, match="M2"):
        compile_plan_llm(make_spec())


def test_unknown_mode_raises() -> None:
    with pytest.raises(CraftModeError):
        compile_plan(make_spec(), mode="magic")


def test_add_endpoint_template_kinds_risk_and_grep_verify() -> None:
    spec = make_spec(
        title="加端点",
        description="新增 GET /users/by-email 查询端点",
        hint="UserController.java",
    )
    plan = compile_plan(spec)
    assert [s.kind for s in plan.steps] == ["understand", "add", "test", "verify"]
    assert plan.risk_classification["public_api"] is True
    assert plan.risk_classification["auth"] is True
    verify = plan.steps[-1]
    assert verify.success_criteria.type == "grep"
    assert verify.success_criteria.value == "/users/by-email"
    assert plan.steps[1].target_files == ["UserController.java"]


def test_fix_bug_template() -> None:
    plan = compile_plan(make_spec(title="修复 double 函数的逻辑错误", hint="calc.py"))
    assert [s.kind for s in plan.steps] == ["understand", "modify", "test", "verify"]
    assert plan.steps[0].target_files == ["calc.py"]
    assert plan.steps[2].success_criteria.type == "test_green"


def test_cache_task_uses_add_template() -> None:
    plan = compile_plan(make_spec(title="给查询加 Redis 缓存"))
    assert [s.kind for s in plan.steps] == ["understand", "add", "test", "verify"]


def test_migration_task_sets_migration_risk() -> None:
    plan = compile_plan(make_spec(title="数据库迁移脚本"))
    assert plan.risk_classification["migration"] is True


def test_auth_keyword_sets_auth_risk() -> None:
    plan = compile_plan(make_spec(title="修 bug", description="涉及鉴权逻辑的缺陷"))
    assert plan.risk_classification["auth"] is True


def test_area_hints_without_dots_are_not_target_files() -> None:
    plan = compile_plan(make_spec(hint="controller/service/repository"))
    assert plan.steps[0].target_files == []


def test_file_like_hints_become_target_files() -> None:
    plan = compile_plan(make_spec(hint="calc.py, tests/test_calc.py"))
    assert plan.steps[0].target_files == ["calc.py", "tests/test_calc.py"]


def test_step_cap_enforced() -> None:
    steps = [
        Step(id="s" + str(i), kind="understand", success_criteria=SuccessCriteria("grep"))
        for i in range(1, 14)
    ]
    with pytest.raises(PlanTooComplexError, match="12"):
        ensure_step_cap(steps)


def test_normal_plans_stay_within_cap() -> None:
    for title in ("加端点", "修 bug", "重构", "加测试", "迁移", "缓存", "随便什么"):
        plan = compile_plan(make_spec(title=title))
        assert len(plan.steps) <= MAX_PLAN_STEPS


def test_budget_alloc_defaults() -> None:
    plan = compile_plan(make_spec())
    assert plan.budget_alloc == {"iterations": 12, "tokens": 200000}


def test_budget_alloc_respects_budget_override() -> None:
    plan = compile_plan(make_spec(), budget=Budget(max_iterations=5, token_budget=1000))
    assert plan.budget_alloc == {"iterations": 5, "tokens": 1000}


def test_plan_serialization_round_trip() -> None:
    plan = compile_plan(make_spec(title="修 bug", hint="calc.py"))
    assert Plan.from_dict(plan.to_dict()) == plan


def test_plan_save_and_reload(tmp_path: Path) -> None:
    plan = compile_plan(make_spec(title="修 bug"))
    target = tmp_path / "out" / "plan.json"
    plan.save(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert Plan.from_dict(data) == plan


def test_plan_from_dict_rejects_bad_step_kind() -> None:
    data = compile_plan(make_spec()).to_dict()
    data["steps"][0]["kind"] = "teleport"
    with pytest.raises(CraftPlanError):
        Plan.from_dict(data)


def test_plan_from_dict_rejects_bad_criteria_type() -> None:
    data = compile_plan(make_spec()).to_dict()
    data["steps"][0]["success_criteria"]["type"] = "vibes"
    with pytest.raises(CraftPlanError):
        Plan.from_dict(data)


def test_plan_from_dict_rejects_missing_steps() -> None:
    data = compile_plan(make_spec()).to_dict()
    del data["steps"]
    with pytest.raises(CraftPlanError):
        Plan.from_dict(data)
