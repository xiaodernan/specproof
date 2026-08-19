"""W113 offline regression tests — no network, no Docker, no real LLM.

Two real SWE-bench LLM run failures drive these tests
(docs/eval/swebench-llm-results-v3.json):

- pallets__flask-4045 FAILED: "apply_edit 拒绝: old 未命中
  (src/flask/helpers.py)" — the model's old-string anchor drifted from the
  real file. Fixes under test: the diagnose/edit-proposal prompt ships the
  current REAL content of every candidate source file (bounded to the
  first 400 lines) with the instruction "quote old strings EXACTLY from
  the file content above", and Editor.apply_edit falls back to a
  whitespace-normalized line match (tabs collapsed, trailing spaces
  stripped) that is applied against the REAL file text.
- pallets__flask-4992 STUCK: "s5|断言值 tomllib 未出现在:
  [tests/test_config.py]" — the verify criterion grepped a TEST file for
  the expected assertion, but the harness applies hidden tests only AFTER
  craft, so that grep can never pass. Fix under test: "assertion appears"
  grep/contains verify criteria search SOURCE files only (src/**, *.py
  outside tests/**); a criterion whose targets are all test files fails
  honestly instead of faking a pass.

Covers:
  (a) a loop with a scripted LLM client receives the real file content in
      the edit prompt, plus the anchor instruction;
  (b) apply_edit's relaxed whitespace match applies when lines differ only
      in trailing whitespace, spliced onto the real file text;
  (c) an ambiguous relaxed match still rejects with the real reason;
  (d) a grep verify criterion targets source files, never tests/**;
  (e) the deterministic no-LLM path keeps the same report shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from craft.editor import EditError, Editor
from craft.llm import LLMClient
from craft.loop import CraftLoop
from craft.planner import Plan, Step, SuccessCriteria, compile_plan
from craft.spec import parse_spec_text
from providers.base import LLMMessage, LLMResponse

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

ANCHOR_INSTRUCTION = "quote old strings EXACTLY from the file content above"


def _verify_plan(targets: list[str], value: str) -> Plan:
    """A verify step shaped like the LLM planner's output for
    pallets__flask-4992: a grep criterion whose target_files include the
    test file the problem statement mentions."""
    return Plan(
        task_title="verify 断言落位",
        mode="deterministic",
        steps=[
            Step(
                id="s1",
                kind="verify",
                target_files=list(targets),
                intent="机械核验断言值出现在目标文件",
                success_criteria=SuccessCriteria("grep", value),
            )
        ],
        risk_classification={
            "auth": False,
            "migration": False,
            "mq": False,
            "public_api": False,
        },
        budget_alloc={"iterations": 2, "tokens": 50_000},
    )


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; records every prompt."""

    def __init__(self, replies: list[str], *, job_id: str = "job-w113") -> None:
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
        self.calls.append({**entry, "job_id": self.job_id, "model": "fake-w113"})
        return LLMResponse(content=reply, usage=usage, model="fake-w113")


# -- (a) the edit prompt ships the real file content + anchor instruction ------


def test_edit_prompt_contains_real_file_content_and_anchor_instruction(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "anchor_marker_4045 = True\n"
        "x = 1" + "  \n" +  # real trailing whitespace, quoted without drift
        "",
        encoding="utf-8",
    )
    proposal = json.dumps(
        {
            "diagnosis": "x 应为 2",
            "edits": [
                {
                    "action": "apply_edit",
                    "path": "src/app.py",
                    "old": "x = 1" + "  ",
                    "new": "x = 2",
                }
            ],
        },
        ensure_ascii=False,
    )
    spec = parse_spec_text(
        "修复 src/app.py 的锚点\n验收: x 应为 2\n影响: src/app.py"
    )
    plan = _verify_plan(["src/app.py"], "x = 2")
    plan = Plan(
        task_title=plan.task_title,
        mode="llm",
        steps=plan.steps,
        risk_classification=plan.risk_classification,
        budget_alloc=plan.budget_alloc,
    )
    client = _ScriptedClient([proposal])
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-anchor",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    report = loop.run()
    assert report["result"] == "DONE"
    assert len(client.sent_prompts) == 1  # valid on the first try: no repair
    prompt = client.sent_prompts[0]
    assert ANCHOR_INSTRUCTION in prompt
    assert "--- src/app.py ---" in prompt
    assert "anchor_marker_4045 = True" in prompt
    assert "x = 1" + "  " in prompt  # the real line, trailing spaces included
    assert "x = 2" in (tmp_path / "src" / "app.py").read_text(encoding="utf-8")


# -- (b)/(c) relaxed whitespace anchor in Editor.apply_edit --------------------


def test_apply_edit_relaxed_whitespace_match_applies_real_text(
    tmp_path: Path,
) -> None:
    # Multi-line anchor whose FIRST line drifted in trailing whitespace:
    # the exact substring misses, the normalized line match anchors on the
    # real text and splices the replacement over the real lines.
    target = tmp_path / "helpers.py"
    target.write_text(
        "def f():\n" + "    value = 1" + "  \n" + "    return value\n",
        encoding="utf-8",
    )
    editor = Editor(tmp_path)
    editor.apply_edit(
        "helpers.py",
        "    value = 1\n    return value",
        "    value = 2\n    return value",
    )
    assert target.read_text(encoding="utf-8") == (
        "def f():\n    value = 2\n    return value\n"
    )
    edit_entries = [entry for entry in editor.audit if entry.action == "edit"]
    assert edit_entries and "空白归一化匹配" in edit_entries[0].detail


def test_apply_edit_ambiguous_relaxed_match_rejects_with_real_reason(
    tmp_path: Path,
) -> None:
    target = tmp_path / "config.py"
    original = "x\t= 1\nx\t=\t1\n"
    target.write_text(original, encoding="utf-8")
    editor = Editor(tmp_path)
    with pytest.raises(EditError, match="归一化"):
        editor.apply_edit("config.py", "x = 1", "x = 2")
    assert target.read_text(encoding="utf-8") == original


# -- (d) grep verify criteria never target test files -------------------------


def test_grep_verify_criterion_targets_source_files_never_tests(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "flask").mkdir(parents=True)
    (tmp_path / "src" / "flask" / "config.py").write_text(
        "import tomllib\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_config.py").write_text(
        "def test_config():\n    return None\n", encoding="utf-8"
    )
    spec = parse_spec_text(
        "配置支持 tomllib\n验收: 断言出现\n影响: tests/test_config.py,src/flask/config.py"
    )
    plan = _verify_plan(["tests/test_config.py", "src/flask/config.py"], "tomllib")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-verify-src",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is True
    assert result is None
    assert evidence["check"] == "grep"
    assert "命中全部目标源文件" in evidence["note"]
    assert "src/flask/config.py" in evidence["note"]
    assert "已排除测试文件" in evidence["note"]
    assert "tests/test_config.py" in evidence["note"]
    assert "reason" not in evidence


def test_grep_verify_criterion_with_only_test_targets_fails_honestly(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_config.py").write_text(
        "def test_config():\n    return None\n", encoding="utf-8"
    )
    spec = parse_spec_text(
        "配置支持 tomllib\n验收: 断言出现\n影响: tests/test_config.py"
    )
    plan = _verify_plan(["tests/test_config.py"], "tomllib")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-verify-only-tests",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is False
    assert result is None
    assert evidence["check"] == "grep"
    assert "无源文件可搜索" in evidence["reason"]
    assert "tests/test_config.py" in evidence["reason"]
    assert "隐藏测试" in evidence["reason"]


# -- (e) deterministic no-LLM path unchanged ----------------------------------


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


def _fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    del step, diagnosis
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def test_deterministic_no_llm_path_report_shape_unchanged(tmp_path: Path) -> None:
    """The deterministic M1 path never builds an LLM prompt: same report
    shape and zero-filled gains as before the W113 changes."""
    _write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    report = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-deterministic",
        fix_registry={"test": _fix_double},
        exec_mode="local",
    ).run()
    assert report["result"] == "DONE"
    assert report["mode"] == "deterministic"
    assert report["gains"] == {
        "tool_call_attempts": 0,
        "tool_call_valid": 0,
        "tool_call_retried": 0,
        "tool_call_success_rate": 0.0,
        "router_fallback_count": 0,
        "cache_hits": 0,
        "judge_persona_applied": 0,
    }
    assert "llm_usage" not in report
    assert report["budget_used"]["tokens"] == 0
    steps = {step["id"]: step for step in report["steps"]}
    assert all(steps[sid]["status"] == "green" for sid in ("s1", "s2", "s3", "s4"))
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
