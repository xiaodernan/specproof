"""SpecCraft M1 — the deterministic skeleton of the autonomous coding agent
(design doc: docs/design/SPECCRAFT_PLAN.md).

M1 scope: spec parsing -> deterministic planning -> atomic editing -> sandboxed
whitelisted execution -> budget-gated plan/execute/verify loop -> checkpoint and
report artifacts under .specraft/. LLM planning/diagnosis (M2), self-verify
(M3) and MySQL persistence (M4) are NOT part of M1: their interfaces are either
absent or fail loudly / degrade honestly, never pretending to be implemented.
"""

from .budget import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_TIMEOUT_MINUTES,
    DEFAULT_TOKEN_BUDGET,
    Budget,
    BudgetError,
)
from .editor import MAX_READ_LINES, AuditEntry, EditError, Editor
from .executor import (
    ALLOWED_COMMANDS,
    CommandNotAllowedError,
    ExecResult,
    Executor,
    FailedTest,
    TestReport,
    extract_pytest_failed_tests,
)
from .llm import (
    DEFAULT_LLM_TOKEN_BUDGET,
    LLMClient,
    LLMUnavailableError,
    extract_json_object,
    resolve_craft_thinking,
)
from .loop import CraftLoop, CraftLoopError, FixFunction, StepState, default_job_id
from .planner import (
    MAX_PLAN_STEPS,
    CraftModeError,
    CraftPlanError,
    Plan,
    PlanTooComplexError,
    Step,
    SuccessCriteria,
    classify_task,
    compile_plan,
    compile_plan_llm,
    ensure_step_cap,
)
from .spec import (
    SpecParseError,
    TaskSpec,
    parse_spec,
    parse_spec_file,
    parse_spec_json,
    parse_spec_text,
)

__all__ = [
    "ALLOWED_COMMANDS",
    "AuditEntry",
    "Budget",
    "BudgetError",
    "CommandNotAllowedError",
    "CraftLoop",
    "CraftLoopError",
    "CraftModeError",
    "CraftPlanError",
    "DEFAULT_LLM_TOKEN_BUDGET",
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_MAX_STEPS",
    "DEFAULT_MAX_TOOL_CALLS",
    "DEFAULT_TIMEOUT_MINUTES",
    "DEFAULT_TOKEN_BUDGET",
    "EditError",
    "Editor",
    "ExecResult",
    "Executor",
    "FailedTest",
    "FixFunction",
    "LLMClient",
    "LLMUnavailableError",
    "MAX_PLAN_STEPS",
    "MAX_READ_LINES",
    "Plan",
    "PlanTooComplexError",
    "SpecParseError",
    "Step",
    "StepState",
    "SuccessCriteria",
    "TaskSpec",
    "TestReport",
    "classify_task",
    "compile_plan",
    "compile_plan_llm",
    "default_job_id",
    "ensure_step_cap",
    "extract_json_object",
    "extract_pytest_failed_tests",
    "parse_spec",
    "parse_spec_file",
    "parse_spec_json",
    "parse_spec_text",
    "resolve_craft_thinking",
]
