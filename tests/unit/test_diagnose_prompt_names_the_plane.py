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
      -> cases 1,2,3,4,6 (5). Case 5 stays green: the two builds it compares differ in
         `failure_diagnosis`, so their text still differs with or without the key.
         Case 6 reddens because the self-check leg copies THIS dict — measured on the
         first witness round, which refused with 4 predicted / 5 measured.
  M2  the no-cache branch says "依赖缓存: 已验证"
      -> case 3 (1) — inventing a positive claim where the sandbox said nothing
  M3  the no-command branch returns a plane-shaped block instead
      -> case 4 (1) — a read-only criterion never ran anything, so it has no plane
  M4  `assemble` folds the variable sections into the stable prefix
      -> case 5 (1) — the semantic cache would then key a "stable" prefix on data
         that changes every iteration
  M5  the plane block drops its `mode` line
      -> cases 1,2,3,6 (4). Case 4 is the no-command branch (nothing to name) and
         case 5's two builds still differ in the cache line.
      Correction kept in the record: M5 was drafted next to the witness script
      rather than here, so only M1-M4 were pre-written in the module; and its first
      prediction (3 reds) missed case 6, which also pins `mode=`. Roster now complete.
  M6  the W44 self-check leg rebuilds its sections without the plane
      -> case 6 (1) — the retry prompt would keep the JSON contract and lose the
         disclosure on exactly the iteration where the model is being steered
  M7  the W44 self-check leg stops appending the envelope contract
      -> case 6 (1). The first draft of this pin asserted the block's FIRST LINE, and
         the arm survived it (0 reds measured): that line is already in the prompt
         without `include_envelope`, so it proved nothing. The pin is positional now —
         the envelope block is the tail of the shipped prompt.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from craft.executor import ExecResult
from craft.loop import CraftLoop
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from craft.tools import ToolRegistry
from providers.prompt_templates import JSON_ACTION_ENVELOPE_BLOCK, assemble, stable_prefix_identical
from providers.toolcheck import ToolCallSelfCheck

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

CACHE_UNARMED = (
    "缓存完整性: 未校验 (NOT VERIFIED) —— profile PYTHON 挂了缓存卷 "
    "specproof-pip-cache, 调用方却没传 cache_dir+cache_manifest"
)

# The model answers the self-check leg with one Action Envelope; the first one is
# refused on purpose so the retry prompt (which must still carry the plane) gets built.
_ENVELOPE_BAD = json.dumps({
    "action": "apply_patch",
    "version": 99,
    "params": {"path": "calc.py", "old": "return x / 2", "new": "return x * 2"},
})
_ENVELOPE_VALID = json.dumps({
    "action": "apply_patch",
    "version": 1,
    "params": {"path": "calc.py", "old": "return x / 2", "new": "return x * 2"},
})


class FakeResponse:
    """LLMResponse stand-in: the loop only reads .content."""

    def __init__(self, content: str) -> None:
        self.content = content


class FakeBudget:
    used = 0.0


class RecordingClient:
    """Recording chat_sync: plays canned envelope answers, keeps every prompt."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.budget = FakeBudget()

    def chat_sync(self, messages: list[object], **kwargs: object) -> FakeResponse:
        prompt = "".join(
            str(message.content) for message in messages if message.role == "user"
        )
        self.prompts.append(prompt)
        return FakeResponse(self.responses.pop(0))

    def stats_report(self) -> dict[str, int]:
        return {"calls": len(self.prompts)}


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


def plane_step() -> Step:
    return Step(
        id="s-plane",
        kind="test",
        target_files=["calc.py"],
        intent="run the acceptance test",
    )


def build_loop(tmp_path: Path, *, llm: bool = False, **kwargs: object) -> CraftLoop:
    (tmp_path / "calc.py").write_text("def double(x):\n    return x / 2\n", encoding="utf-8")
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    if llm:
        plan = dataclasses.replace(plan, mode="llm")
    return CraftLoop(spec, plan, tmp_path, job_id="job-plane", exec_mode="local", **kwargs)


@pytest.fixture
def loop(tmp_path: Path) -> CraftLoop:
    return build_loop(tmp_path)


def context(
    loop: CraftLoop,
    result: ExecResult | None,
    diagnosis: str = "预期 6 实得 1",
    *,
    envelope_mode: bool = False,
) -> dict[str, str]:
    return loop._diagnose_context(plane_step(), result, diagnosis, envelope_mode=envelope_mode)


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


def test_the_self_check_retry_prompt_keeps_the_plane(tmp_path: Path) -> None:
    """#144: `craft/loop.py` has exactly two diagnose assemble sites — the proposal leg
    and the W44 self-check leg, whose retry prompt is the one a future 'ship only the
    JSON contract' optimisation would trim. Both prompts here come out of shipped code."""
    client = RecordingClient([_ENVELOPE_BAD, _ENVELOPE_VALID])
    registry = ToolRegistry(tmp_path)
    loop = build_loop(
        tmp_path,
        llm=True,
        client=client,
        tool_registry=registry,
        tool_call_self_check=ToolCallSelfCheck.from_registry(registry),
    )
    result = exec_result(cache_note=CACHE_UNARMED)
    variables = context(loop, result, "预期 6 实得 1", envelope_mode=True)
    loop._llm_fix_envelope(client, "STABLE", variables, plane_step(), "预期 6 实得 1")

    assert len(client.prompts) == 2, (
        f"expected the first envelope to be refused and one retry, got "
        f"{len(client.prompts)} prompt(s)"
    )
    envelope_block = JSON_ACTION_ENVELOPE_BLOCK.strip()
    for index, prompt in enumerate(client.prompts):
        assert "[execution_plane]" in prompt, f"prompt {index} lost the plane section"
        assert CACHE_UNARMED in prompt, f"prompt {index} lost the cache wording"
        assert "mode=docker_sandbox" in prompt, f"prompt {index} lost the mode"
        # Positional pin: matching the block's first line proved nothing — the
        # envelope-mode context quotes it even with include_envelope=False (arm M7
        # survived that draft), so the claim has to be where the block sits.
        assert prompt.endswith(envelope_block), f"prompt {index} lost the envelope tail"
    assert "[self_check_repair]" in client.prompts[1], "the retry carried no repair instruction"
    assert "[self_check_repair]" not in client.prompts[0], "the first prompt was already a retry"
