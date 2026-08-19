"""craft/planner.py plan-versioning tests (计划书 §5.3: 计划变更必须版本化).

The version ledger (PlanVersion + record_plan_change) must freeze old plan,
new plan identity, reason, approval and budget delta, and
plan_change_requires_approval must flag material revisions — so a model
cannot rewrite its plan mid-run to dodge the original approval.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from craft.planner import (
    CraftPlanError,
    Plan,
    PlanTooComplexError,
    PlanVersion,
    Step,
    SuccessCriteria,
    compile_plan,
    plan_change_requires_approval,
    plan_digest,
    record_plan_change,
)
from craft.spec import TaskSpec


def make_spec(title: str = "任务", hint: str = "") -> TaskSpec:
    return TaskSpec(
        title=title,
        description="",
        acceptance_criteria=[],
        affected_area_hint=hint,
    )


def make_plan(title: str = "修 bug", hint: str = "calc.py") -> Plan:
    return compile_plan(make_spec(title=title, hint=hint))


def annotate(plan: Plan, intent: str) -> Plan:
    """Cosmetic revision: first step's intent text only."""
    return replace(plan, steps=[replace(plan.steps[0], intent=intent)])


def test_record_plan_change_records_all_fields() -> None:
    old_plan = make_plan()
    new_plan = annotate(old_plan, "重点阅读 calc.py 的边界处理")
    record = record_plan_change(
        old_plan,
        new_plan,
        reason="模型调整了 understand 步骤的说明",
        budget_delta={"tokens": 50_000},
        version=3,
        approved_by="reviewer@example.com",
    )
    assert record.plan_id == f"{old_plan.mode}:{old_plan.task_title}"
    assert record.version == 3
    assert record.base_plan_digest == plan_digest(old_plan)
    assert record.reason == "模型调整了 understand 步骤的说明"
    assert record.approved_by == "reviewer@example.com"
    assert record.budget_delta == {"tokens": 50_000}
    stamp = datetime.fromisoformat(record.created_at)
    assert stamp.tzinfo is not None


def test_record_plan_change_accepts_explicit_plan_id_and_stamp() -> None:
    old_plan = make_plan()
    new_plan = annotate(old_plan, "调整说明")
    record = record_plan_change(
        old_plan,
        new_plan,
        reason="调整说明",
        plan_id="job-7:plan-1",
        created_at="2026-08-18T09:30:00+00:00",
    )
    assert record.plan_id == "job-7:plan-1"
    assert record.version == 1
    assert record.approved_by == ""
    assert record.created_at == "2026-08-18T09:30:00+00:00"


def test_budget_delta_derived_from_budget_alloc_when_omitted() -> None:
    old_plan = make_plan()
    new_plan = replace(old_plan, budget_alloc={"iterations": 12, "tokens": 250_000})
    record = record_plan_change(old_plan, new_plan, reason="扩大 token 预算")
    assert record.budget_delta == {"tokens": 50_000}


def test_adding_a_step_requires_approval() -> None:
    old_plan = make_plan()
    extra = Step(
        id="s5",
        kind="verify",
        intent="补充审计核验",
        success_criteria=SuccessCriteria("grep"),
    )
    new_plan = replace(old_plan, steps=[*old_plan.steps, extra])
    assert plan_change_requires_approval(old_plan, new_plan) is True


def test_replacing_a_step_with_a_new_id_requires_approval() -> None:
    old_plan = make_plan()
    swapped = Step(
        id="s9",
        kind=old_plan.steps[0].kind,
        target_files=list(old_plan.steps[0].target_files),
        intent=old_plan.steps[0].intent,
        success_criteria=old_plan.steps[0].success_criteria,
    )
    new_plan = replace(old_plan, steps=[swapped, *old_plan.steps[1:]])
    assert plan_change_requires_approval(old_plan, new_plan) is True


def test_scope_expansion_to_new_paths_requires_approval() -> None:
    old_plan = make_plan(hint="calc.py")
    widened = replace(
        old_plan,
        steps=[
            replace(old_plan.steps[0], target_files=["calc.py", "secret_store.py"]),
            *old_plan.steps[1:],
        ],
    )
    assert plan_change_requires_approval(old_plan, widened) is True
    swapped = replace(
        old_plan,
        steps=[
            replace(old_plan.steps[0], target_files=["auth.py"]),
            *old_plan.steps[1:],
        ],
    )
    assert plan_change_requires_approval(old_plan, swapped) is True


def test_adding_an_approval_flag_requires_approval() -> None:
    old_plan = make_plan()
    flagged = replace(
        old_plan,
        risk_classification={**old_plan.risk_classification, "migration": True},
    )
    assert plan_change_requires_approval(old_plan, flagged) is True


def test_removing_an_approval_flag_requires_approval() -> None:
    old_plan = make_plan(title="加端点", hint="UserController.java")
    assert old_plan.risk_classification["auth"] is True
    unflagged = replace(
        old_plan,
        risk_classification={**old_plan.risk_classification, "auth": False},
    )
    assert plan_change_requires_approval(old_plan, unflagged) is True


def test_raising_budget_requires_approval() -> None:
    old_plan = make_plan()
    raised = replace(old_plan, budget_alloc={"iterations": 12, "tokens": 300_000})
    assert plan_change_requires_approval(old_plan, raised) is True


def test_cosmetic_step_reorder_needs_no_approval() -> None:
    old_plan = make_plan()
    reordered = replace(old_plan, steps=list(reversed(old_plan.steps)))
    assert plan_change_requires_approval(old_plan, reordered) is False


def test_annotation_only_change_needs_no_approval() -> None:
    old_plan = make_plan()
    revised = annotate(old_plan, "重点阅读 calc.py 的边界处理")
    assert plan_change_requires_approval(old_plan, revised) is False


def test_narrowing_scope_and_lowering_budget_need_no_approval() -> None:
    old_plan = make_plan(hint="calc.py, extra.py")
    narrowed = replace(
        old_plan,
        steps=[
            replace(old_plan.steps[0], target_files=["calc.py"]),
            *old_plan.steps[1:],
        ],
        budget_alloc={"iterations": 8, "tokens": 100_000},
    )
    assert plan_change_requires_approval(old_plan, narrowed) is False


def test_revision_with_dependency_cycle_is_rejected() -> None:
    old_plan = make_plan()
    cyclic = Plan(
        task_title=old_plan.task_title,
        mode=old_plan.mode,
        steps=[
            Step(id="s1", kind="understand", deps=["s2"]),
            Step(id="s2", kind="modify"),
        ],
        risk_classification=dict(old_plan.risk_classification),
        budget_alloc=dict(old_plan.budget_alloc),
    )
    with pytest.raises(CraftPlanError, match="次序非法"):
        record_plan_change(old_plan, cyclic, reason="引入后向依赖")


def test_revision_with_duplicate_step_ids_is_rejected() -> None:
    old_plan = make_plan()
    duplicate = Plan(
        task_title=old_plan.task_title,
        mode=old_plan.mode,
        steps=[
            Step(id="s1", kind="understand"),
            Step(id="s1", kind="verify"),
        ],
        risk_classification=dict(old_plan.risk_classification),
        budget_alloc=dict(old_plan.budget_alloc),
    )
    with pytest.raises(CraftPlanError, match="重复"):
        record_plan_change(old_plan, duplicate, reason="复制了步骤 id")


def test_revision_over_step_cap_is_rejected() -> None:
    old_plan = make_plan()
    over = Plan(
        task_title=old_plan.task_title,
        mode=old_plan.mode,
        steps=[Step(id=f"s{index}", kind="understand") for index in range(1, 14)],
        risk_classification=dict(old_plan.risk_classification),
        budget_alloc=dict(old_plan.budget_alloc),
    )
    with pytest.raises(PlanTooComplexError, match="12"):
        record_plan_change(old_plan, over, reason="步骤超限")


def test_plan_digest_is_stable_and_canonical() -> None:
    plan = make_plan()
    assert plan_digest(plan) == plan_digest(plan)
    assert plan_digest(Plan.from_dict(plan.to_dict())) == plan_digest(plan)
    data = plan.to_dict()
    data["steps"][0] = dict(reversed(list(data["steps"][0].items())))
    reordered = Plan.from_dict(dict(reversed(list(data.items()))))
    assert plan_digest(reordered) == plan_digest(plan)


def test_plan_digest_reflects_any_content_change() -> None:
    plan = make_plan()
    assert plan_digest(annotate(plan, "重点阅读 calc.py 的边界处理")) != plan_digest(plan)
    assert (
        plan_digest(replace(plan, steps=list(reversed(plan.steps)))) != plan_digest(plan)
    )


def test_plan_version_serialization_round_trip() -> None:
    old_plan = make_plan()
    new_plan = annotate(old_plan, "调整说明")
    record = record_plan_change(
        old_plan, new_plan, reason="调整说明", approved_by="reviewer@example.com"
    )
    assert PlanVersion.from_dict(record.to_dict()) == record


def test_plan_version_from_dict_rejects_bad_digest() -> None:
    old_plan = make_plan()
    record = record_plan_change(old_plan, annotate(old_plan, "调整"), reason="调整")
    data = record.to_dict()
    data["base_plan_digest"] = "not-a-digest"
    with pytest.raises(CraftPlanError, match="sha256"):
        PlanVersion.from_dict(data)
