"""#143: the diagnose prompt has to say which plane produced the failure.

The model is asked to fix a failing check with `failure_output` in front of it and
no word about where that output came from (W166 closed the evidence/console half of
this; `#140`/`#141`/`#142` closed the report/log readers). When the honest answer is
"this run consumed an unverified dependency cache", a prompt that cannot say so
sends the proposal loop back to editing source code — which is exactly the failure
mode #7's guard was built to make visible.

Why a new context key is enough: `providers/prompt_templates.py:assemble` renders
every entry of the variable dict generically (`sections = [f"[{key}]\\n{value}" for
key, value in sorted(variable_data.items())]`), measured before writing this, so the
value reaches the model with no template edit and no OpenAPI change.

Mutation arms, red sets predicted by which branch each case walks (not by the words
in a case name):

  M1  drop `"execution_plane"` from the diagnose context
      -> cases 1,2,3,4 (4). Case 5 stays green: the two builds it compares differ in
         `failure_diagnosis`, so their text still differs with or without the key.
  M2  the no-cache branch says "依赖缓存: 已验证"
      -> case 3 (1) — inventing a positive claim where the sandbox said nothing
  M3  the no-command branch returns a plane-shaped block instead
      -> case 4 (1) — a read-only criterion never ran anything, so it has no plane
  M4  `assemble` folds the variable sections into the stable prefix
      -> case 5 (1) — the semantic cache would then key a "stable" prefix on data
         that changes every iteration
"""

from __future__ import annotations

from pathlib import Path

import pytest

from craft.executor import ExecResult
from craft.loop import CraftLoop
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from providers.prompt_templates import assemble, stable_prefix_identical

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

CACHE_UNARMED = (
    "缓存完整性: 未校验 (NOT VERIFIED) —— profile PYTHON 挂了缓存卷 "
    "specproof-pip-cache, 调用方却没传 cache_dir+cache_manifest"
)


def exec_result(*, cache_note: str, mode: str = "docker_sandbox") -> ExecResult:
    return ExecResult(
        command=["python", "-m", "pytest", "-q"],
        exit_code=1,
        stdout="FAILED test_calc.py::test_double - assert 1 == 6",
        stderr="",
        output_tail="FAILED test_calc.py::test_double - assert 1 == 6",
        truncated=False,
        error="",
        mode=mode,
        cache_note=cache_note,
    )


@pytest.fixture
def loop(tmp_path: Path) -> CraftLoop:
    (tmp_path / "calc.py").write_text("def double(x):\n    return x / 2\n", encoding="utf-8")
    spec = parse_spec_text(FIX_SPEC)
    return CraftLoop(spec, compile_plan(spec), tmp_path, job_id="job-plane", exec_mode="local")


def context(loop: CraftLoop, result: ExecResult | None, diagnosis: str = "预期 6 实得 1"):
    step = Step(
        id="s-plane",
        kind="test",
        target_files=["calc.py"],
        intent="run the acceptance test",
    )
    return loop._diagnose_context(step, result, diagnosis, envelope_mode=False)


def test_the_new_key_reaches_the_model_through_assemble(loop: CraftLoop) -> None:
    """The claim is 'the model reads it', so the case renders the shipped prompt."""
    variables = context(loop, exec_result(cache_note=CACHE_UNARMED))
    built = assemble("STABLE", "diagnose", variables, include_envelope=False)
    assert "[execution_plane]" in built.text, f"section never rendered: {built.text[-600:]!r}"
    assert CACHE_UNARMED in built.text
    assert "mode=docker_sandbox" in built.text


def test_a_cache_disclosure_rides_verbatim(loop: CraftLoop) -> None:
    block = context(loop, exec_result(cache_note=CACHE_UNARMED))["execution_plane"]
    assert CACHE_UNARMED in block, f"paraphrased the sandbox's own words: {block!r}"
    assert "mode=docker_sandbox" in block, f"plane missing: {block!r}"


def test_no_mounted_cache_says_so_without_inventing_one(loop: CraftLoop) -> None:
    block = context(loop, exec_result(cache_note=""))["execution_plane"]
    assert "未挂载" in block, f"absence not stated: {block!r}"
    assert "依赖缓存: 已验证" not in block, f"invented a positive claim: {block!r}"
    assert "mode=docker_sandbox" in block, f"plane missing: {block!r}"


def test_a_check_that_ran_no_command_says_it_ran_no_command(loop: CraftLoop) -> None:
    block = context(loop, None)["execution_plane"]
    assert "没有执行任何命令" in block, f"hid the read-only criterion: {block!r}"
    assert "mode=" not in block, f"claimed a plane for a run that had none: {block!r}"
    assert "依赖缓存" not in block, f"spoke about a cache it never touched: {block!r}"


def test_the_variable_does_not_move_the_stable_prefix(loop: CraftLoop) -> None:
    """Prompt-cache invariant: per-iteration data must stay behind the prefix, so
    adding this key must not make every diagnose call a cache miss on the prefix."""
    cached = exec_result(cache_note=CACHE_UNARMED)
    plain = exec_result(cache_note="")
    first = assemble("STABLE", "diagnose", context(loop, cached, "A"))
    second = assemble("STABLE", "diagnose", context(loop, plain, "B"))
    assert stable_prefix_identical(first, second), "the plane moved into the stable prefix"
    assert first.text != second.text, (
        "two different planes produced identical prompts — the disclosure is not riding"
    )
