"""Offline regression tests for the W112 test-file edit guard (no network/Docker/LLM).

The real SWE-bench LLM re-run (docs/eval/swebench-llm-results-v2.json) left both
pallets__flask instances stuck with honest signatures ('pytest.raises(ValueError)
not present in tests/test_blueprints.py' / 'tomllib not present in
tests/test_config.py') because the model kept proposing edits to TEST files —
adding the assertions the hidden tests expect — instead of fixing the source.
The harness applies each instance's test patch itself, so craft must never
create or modify test files.

Covers:

- is_test_file_path: tests/**, test_*.py, *_test.py (backslash-normalized);
- validate_edit_proposal rejects any test-file edit op with the stable code
  TEST_FILE_FORBIDDEN, and the repair instruction is a source-only one;
- a proposal editing source code still passes validation;
- the CraftLoop diagnose-fix flow arms exactly ONE repair round-trip on a
  test-file proposal (scripted client): a second test-file proposal gives up
  with the stable code, while a corrected source fix converges to DONE.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from craft.llm import LLMClient
from craft.loop import CraftLoop
from craft.planner import compile_plan
from craft.spec import parse_spec_text
from providers.base import LLMMessage, LLMResponse
from providers.toolcheck import (
    CODE_TEST_FILE_FORBIDDEN,
    EditProposalSelfCheck,
    edit_retry_instruction,
    is_test_file_path,
    validate_edit_proposal,
)

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

TEST_FILE_EDIT_JSON = json.dumps(
    {
        "diagnosis": "hidden test expects an assertion, add it",
        "edits": [
            {
                "action": "apply_edit",
                "path": "tests/test_x.py",
                "old": "def test_x():",
                "new": "def test_x():\n    assert True",
            }
        ],
    },
    ensure_ascii=False,
)

VALID_SOURCE_EDIT_JSON = json.dumps(
    {
        "diagnosis": "double() 把乘法写成了除法, 翻转操作符即可",
        "edits": [
            {
                "action": "apply_edit",
                "path": "calc.py",
                "old": "return x / 2",
                "new": "return x * 2",
            }
        ],
    },
    ensure_ascii=False,
)


def _proposal(path: str, *, action: str = "apply_edit") -> dict[str, Any]:
    """One-edit proposal envelope targeting the given repo-relative path."""
    if action == "write_file":
        return {"diagnosis": "d", "edits": [{"action": "write_file", "path": path, "new": "x = 1"}]}
    return {
        "diagnosis": "d",
        "edits": [{"action": "apply_edit", "path": path, "old": "a", "new": "b"}],
    }


# -- pattern helper ------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_x.py",
        "tests/deep/nested/test_x.py",
        "test_x.py",
        "x_test.py",
        "src/test_helpers.py",
        r"tests\test_x.py",  # Windows separator (raw string keeps the backslash)
        "./tests/test_x.py",
    ],
)
def test_is_test_file_path_matches_test_patterns(path: str) -> None:
    assert is_test_file_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "calc.py",
        "src/calc.py",
        "src/flask/blueprints.py",
        "src/flask/config.py",
        "tests.py",
        "contest.py",
        "test_notes.txt",
    ],
)
def test_is_test_file_path_lets_source_pass(path: str) -> None:
    assert is_test_file_path(path) is False


# -- validator rule ------------------------------------------------------------


def test_validate_edit_proposal_rejects_test_file_edit() -> None:
    outcome = validate_edit_proposal(_proposal("tests/test_x.py"))
    assert outcome.status == "retry"
    assert outcome.code == CODE_TEST_FILE_FORBIDDEN
    assert "tests/test_x.py" in outcome.message
    assert "源代码" in outcome.message  # tells the LLM to fix source instead


def test_validate_edit_proposal_rejects_test_file_write() -> None:
    outcome = validate_edit_proposal(_proposal("tests/test_new.py", action="write_file"))
    assert outcome.status == "retry"
    assert outcome.code == CODE_TEST_FILE_FORBIDDEN


def test_validate_edit_proposal_rejects_later_test_file_op() -> None:
    """One forbidden op in the middle rejects the whole proposal."""
    proposal = {
        "diagnosis": "d",
        "edits": [
            {"action": "apply_edit", "path": "src/calc.py", "old": "a", "new": "b"},
            {"action": "apply_edit", "path": "tests/test_x.py", "old": "c", "new": "d"},
        ],
    }
    outcome = validate_edit_proposal(proposal)
    assert outcome.status == "retry"
    assert outcome.code == CODE_TEST_FILE_FORBIDDEN
    assert "edits[1]" in outcome.message


def test_validate_edit_proposal_accepts_source_edit() -> None:
    outcome = validate_edit_proposal(_proposal("src/flask/blueprints.py"))
    assert outcome.status == "valid"
    assert outcome.code == ""


# -- repair instruction --------------------------------------------------------


def test_test_file_retry_instruction_is_source_only() -> None:
    outcome = validate_edit_proposal(_proposal("tests/test_x.py"))
    instruction = edit_retry_instruction(outcome)
    assert "[TEST_FILE_FORBIDDEN]" in instruction
    assert "source-only" in instruction
    assert "hidden" in instruction
    assert "harness" in instruction


def test_other_retry_instruction_keeps_generic_schema() -> None:
    outcome = validate_edit_proposal({"diagnosis": "d", "changes": []})
    instruction = edit_retry_instruction(outcome)
    assert "[LLM_PROPOSAL_INVALID]" in instruction
    assert '"edits"' in instruction
    assert "source-only" not in instruction


def test_edit_proposal_self_check_arms_one_repair_then_give_up_on_test_file() -> None:
    checker = EditProposalSelfCheck()
    instructions: list[str | None] = []

    def produce(instruction: str | None) -> object:
        instructions.append(instruction)
        return _proposal("tests/test_x.py")

    outcome = checker.check_with_retry(produce)
    assert outcome.status == "give_up"
    assert outcome.code == CODE_TEST_FILE_FORBIDDEN
    assert instructions[0] is None  # first call carries no instruction
    assert "source-only" in (instructions[1] or "")
    assert checker.metrics()["give_ups"] == 1


# -- loop-level flow (scripted client, no network) ------------------------------


def _write_fixture_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
        '    return "hello " + name\n',
        encoding="utf-8",
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
    )


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; records every prompt."""

    def __init__(self, replies: list[str], *, job_id: str = "job-guard") -> None:
        super().__init__(provider=None, token_budget=100_000, job_id=job_id)
        self._replies = list(replies)
        self.sent_prompts: list[str] = []

    def chat_sync(
        self,
        messages: list[LLMMessage],
        *,
        label: str,
        kind: str | None = None,
        job_id: str = "",
        step_id: str = "",
        thinking: bool = False,
        response_format: dict[str, Any] | None = None,
        estimated_prompt_tokens: int = 0,
        timeout: float | None = None,
    ) -> LLMResponse:
        del kind, job_id, step_id, thinking, estimated_prompt_tokens, timeout
        del response_format
        self.sent_prompts.append(messages[0].content)
        reply = self._replies[min(len(self.sent_prompts) - 1, len(self._replies) - 1)]
        usage = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        entry = self.budget.record(usage, label=label)
        self.calls.append({**entry, "job_id": self.job_id, "model": "fake-guard"})
        return LLMResponse(content=reply, usage=usage, model="fake-guard")


def _run_guard_loop(
    tmp_path: Path, replies: list[str]
) -> tuple[CraftLoop, _ScriptedClient, dict[str, Any]]:
    _write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    client = _ScriptedClient(replies)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-guard",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    return loop, client, loop.run()


def test_loop_test_file_proposal_arms_exactly_one_repair_then_fails_with_stable_code(
    tmp_path: Path,
) -> None:
    _loop, client, report = _run_guard_loop(
        tmp_path, [TEST_FILE_EDIT_JSON, TEST_FILE_EDIT_JSON]
    )
    assert report["result"] == "FAILED"
    failed = [step for step in report["steps"] if step["status"] == "failed"]
    assert len(failed) == 1
    reason = str(failed[0]["evidence"]["reason"])
    assert "[TEST_FILE_FORBIDDEN]" in reason
    assert len(client.sent_prompts) == 2  # exactly ONE repair round-trip
    assert "source-only" in client.sent_prompts[1]
    assert "hidden tests are applied by the harness" in client.sent_prompts[0]
    # nothing was edited
    assert "return x / 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


def test_loop_test_file_proposal_repair_converges_on_source_fix(tmp_path: Path) -> None:
    _loop, client, report = _run_guard_loop(
        tmp_path, [TEST_FILE_EDIT_JSON, VALID_SOURCE_EDIT_JSON]
    )
    assert report["result"] == "DONE"
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert len(client.sent_prompts) == 2  # rejected once, then the corrected fix
    assert "source-only" in client.sent_prompts[1]
    assert "hidden tests are applied by the harness" in client.sent_prompts[0]
