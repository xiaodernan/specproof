"""craft/schemas.py unit tests — validation, versioning, adapters, DAG gates."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from craft.planner import Step, SuccessCriteria, compile_plan, ensure_step_cap
from craft.schemas import (
    SCHEMA_VERSION,
    AgentTask,
    Approval,
    Artifact,
    ChangeBundle,
    PlanSchema,
    SchemaModel,
    StepSchema,
    TestResult,
    ToolCall,
    ToolResult,
    agent_task_from_spec,
    plan_from_schema,
    plan_to_schema,
    sha256_hex,
    spec_from_agent_task,
    step_from_schema,
    step_to_schema,
    valid_digest,
)
from craft.spec import TaskSpec, parse_spec_text

SPEC = parse_spec_text(
    "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"
)


# -- SchemaModel base -----------------------------------------------------


def test_schema_version_pins_current_version() -> None:
    assert SchemaModel().schema_version == SCHEMA_VERSION
    assert SCHEMA_VERSION == 1


def test_schema_version_rejects_future_versions() -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        AgentTask(
            task_id="t1",
            task_text="do it",
            repo="r",
            schema_version=2,  # type: ignore[call-arg]
        )


# -- AgentTask ---------------------------------------------------------------


def test_agent_task_minimal_and_defaults() -> None:
    task = AgentTask(task_id="t1", task_text="do it", repo="r")
    assert task.task_id == "t1"
    assert task.execution_mode == "plan_only"
    assert task.network_policy == "deny"
    assert task.model_policy == "default"
    assert task.budget == {}
    assert task.desired_checks == []
    assert task.idempotency_key == ""


def test_agent_task_requires_task_id_text_repo() -> None:
    with pytest.raises(ValidationError, match="task_id"):
        AgentTask(task_text="do it", repo="r")
    with pytest.raises(ValidationError, match="task_text"):
        AgentTask(task_id="t1", repo="r")
    with pytest.raises(ValidationError, match="repo"):
        AgentTask(task_id="t1", task_text="do it")


def test_agent_task_rejects_bad_execution_mode() -> None:
    with pytest.raises(ValidationError, match="execution_mode"):
        AgentTask(task_id="t1", task_text="x", repo="r", execution_mode="yolo")


def test_agent_task_budget_values_non_negative() -> None:
    with pytest.raises(ValidationError, match="budget"):
        AgentTask(task_id="t1", task_text="x", repo="r", budget={"minutes": -1})
    ok = AgentTask(task_id="t1", task_text="x", repo="r", budget={"minutes": 20})
    assert ok.budget["minutes"] == 20


def test_agent_task_json_round_trip() -> None:
    task = AgentTask(
        task_id="t1",
        task_text="do it",
        repo="r",
        base_sha="abc",
        execution_mode="full_auto",
        desired_checks=["pytest"],
        idempotency_key="k",
    )
    restored = AgentTask.model_validate_json(task.model_dump_json())
    assert restored == task


def test_agent_task_from_spec_and_back() -> None:
    task = agent_task_from_spec(
        SPEC, task_id="job-1", repo="repo", execution_mode="full_auto"
    )
    assert task.task_id == "job-1"
    assert task.task_text.startswith("修复 double 函数的逻辑错误")
    spec = spec_from_agent_task(task)
    assert spec.title == SPEC.title
    assert spec.acceptance_criteria == task.desired_checks
    assert spec.affected_area_hint == ""


def test_agent_task_from_spec_rejects_unknown_mode() -> None:
    from craft.schemas import SchemaError

    with pytest.raises(SchemaError, match="execution_mode"):
        agent_task_from_spec(SPEC, task_id="t", repo="r", execution_mode="nope")


def test_spec_from_agent_task_requires_text() -> None:
    from craft.schemas import SchemaError

    with pytest.raises(SchemaError, match="task_text"):
        spec_from_agent_task(AgentTask(task_id="t", task_text="   ", repo="r"))


# -- ToolCall / ToolResult ----------------------------------------------------


def test_tool_call_validation() -> None:
    call = ToolCall(tool="read_file", version=1, call_id="c1")
    assert call.arguments == {}
    assert call.requires_approval is False
    with pytest.raises(ValidationError, match="version"):
        ToolCall(tool="read_file", version=0, call_id="c1")
    with pytest.raises(ValidationError, match="call_id"):
        ToolCall(tool="read_file", version=1, call_id="")
    with pytest.raises(ValidationError, match="tool"):
        ToolCall(tool="", version=1, call_id="c1")


def test_tool_call_budget_cost_non_negative() -> None:
    with pytest.raises(ValidationError, match="budget_cost"):
        ToolCall(tool="t", version=1, call_id="c", budget_cost={"seconds": -1})


def test_tool_result_defaults_and_statuses() -> None:
    result = ToolResult()
    assert result.status == "ok"
    assert result.duration == 0.0
    assert result.security_tags == []
    with pytest.raises(ValidationError, match="status"):
        ToolResult(status="exploded")
    with pytest.raises(ValidationError, match="duration"):
        ToolResult(duration=-0.1)


def test_tool_result_round_trip_preserves_nested_data() -> None:
    result = ToolResult(
        status="ok",
        exit_code=0,
        summary="[ok] done",
        output_head="head",
        output_tail="tail",
        truncated=True,
        artifact_refs=["a1"],
        duration=1.5,
        security_tags=["untrusted"],
    )
    restored = ToolResult.model_validate_json(result.model_dump_json())
    assert restored == result


# -- Approval -----------------------------------------------------------------


def test_approval_defaults_and_states() -> None:
    approval = Approval(action="run_test")
    assert approval.state == "pending"
    assert approval.risk == "medium"
    with pytest.raises(ValidationError, match="state"):
        Approval(action="x", state="maybe")
    with pytest.raises(ValidationError, match="risk"):
        Approval(action="x", risk="extreme")


# -- Artifact -----------------------------------------------------------------


def test_artifact_digest_must_be_sha256_hex() -> None:
    digest = sha256_hex(b"payload")
    assert valid_digest(digest)
    artifact = Artifact(kind="diff", digest=digest, ref="a.patch", size=10)
    assert artifact.size == 10
    with pytest.raises(ValidationError, match="digest"):
        Artifact(kind="diff", digest="not-hex", ref="a.patch", size=10)
    with pytest.raises(ValidationError, match="digest"):
        Artifact(kind="diff", digest=digest[:63], ref="a.patch", size=10)
    with pytest.raises(ValidationError, match="size"):
        Artifact(kind="diff", digest=digest, ref="a.patch", size=-1)


# -- ChangeBundle -------------------------------------------------------------


def test_change_bundle_minimal() -> None:
    bundle = ChangeBundle(task_id="job-1")
    assert bundle.plan_version == 1
    assert bundle.changed_files == []
    assert bundle.specproof_result is None
    with pytest.raises(ValidationError, match="plan_version"):
        ChangeBundle(task_id="job-1", plan_version=0)


def test_change_bundle_full_round_trip() -> None:
    bundle = ChangeBundle(
        task_id="job-1",
        changed_files=["calc.py"],
        diff="--- a/calc.py",
        test_results=[TestResult(command="pytest", exit_code=0, passed=True)],
        risks=["并发"],
        unverified=["性能"],
        rollback="git checkout calc.py",
        specproof_result={"status": "passed"},
    )
    restored = ChangeBundle.model_validate_json(bundle.model_dump_json())
    assert restored == bundle
    assert restored.test_results[0].passed is True


def test_change_bundle_rejects_bad_test_result() -> None:
    with pytest.raises(ValidationError, match="command"):
        ChangeBundle(task_id="j", test_results=[TestResult(command="", exit_code=0, passed=False)])


# -- Step / Plan adapters -----------------------------------------------------


def test_step_schema_round_trip() -> None:
    step = Step(
        id="s2",
        kind="modify",
        target_files=["calc.py"],
        intent="修逻辑",
        success_criteria=SuccessCriteria("compile"),
        deps=["s1"],
    )
    schema = step_to_schema(step)
    assert schema.kind == "modify"
    assert step_from_schema(schema) == step


def test_step_schema_rejects_bad_kind_and_criteria() -> None:
    with pytest.raises(ValidationError, match="kind"):
        StepSchema(
            id="s1",
            kind="explode",
            success_criteria={"type": "grep", "value": ""},
        )
    with pytest.raises(ValidationError, match="type"):
        StepSchema(id="s1", kind="verify", success_criteria={"type": "magic", "value": ""})


def test_plan_schema_round_trip_deterministic() -> None:
    plan = compile_plan(SPEC)
    schema = plan_to_schema(plan)
    assert schema.steps
    restored = plan_from_schema(schema)
    assert restored == plan
    assert restored.mode == "deterministic"


def test_plan_from_schema_rejects_duplicate_ids() -> None:
    from craft.planner import CraftPlanError

    schema = plan_to_schema(compile_plan(SPEC))
    dup = PlanSchema(
        task_title="t",
        mode="llm",
        steps=[
            schema.steps[0].model_dump(),
            schema.steps[0].model_dump(),  # same id twice
        ],
    )
    with pytest.raises(CraftPlanError, match="重复"):
        plan_from_schema(dup)


def test_plan_from_schema_rejects_cycle_deps() -> None:
    from craft.planner import CraftPlanError

    base = compile_plan(SPEC).steps
    steps = [step_to_schema(step) for step in base[:2]]
    # s2 depends on s2 -> cycle-like illegal dependency.
    steps[1] = StepSchema(
        id=steps[1].id,
        kind=steps[1].kind,
        success_criteria=steps[1].success_criteria,
        deps=[steps[1].id],
    )
    with pytest.raises(CraftPlanError, match="次序非法|不存在"):
        plan_from_schema(PlanSchema(task_title="t", mode="llm", steps=steps))


def test_plan_from_schema_enforces_step_cap() -> None:
    from craft.planner import CraftPlanError, PlanTooComplexError

    step = step_to_schema(compile_plan(SPEC).steps[0])
    steps = [step.model_copy(update={"id": f"s{index}"}) for index in range(13)]
    with pytest.raises((CraftPlanError, PlanTooComplexError), match="12"):
        plan_from_schema(PlanSchema(task_title="t", mode="llm", steps=steps))


def test_ensure_step_cap_still_shared_with_planner() -> None:
    plan = compile_plan(SPEC)
    assert ensure_step_cap(plan.steps) == plan.steps


def test_spec_round_trip_keeps_acceptance_criteria() -> None:
    spec = TaskSpec(title="t", description="d", acceptance_criteria=["a1"])
    task = agent_task_from_spec(spec, task_id="x", repo="r", desired_checks=["a1"])
    assert spec_from_agent_task(task).acceptance_criteria == ["a1"]
