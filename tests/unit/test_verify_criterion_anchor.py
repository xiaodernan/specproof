"""W114 offline regression tests — no network, no Docker, no real LLM.

Real SWE-bench LLM run evidence (docs/eval/swebench-llm-results-v4.json):

- pallets__flask-4045 STUCK at verify: the verify step's grep criterion
  extracted a degenerate assertion value ('.') and targeted a test file
  (signature 's2|断言值 . 无源文件可搜索: 目标 [tests/test_blueprints.py]
  均为测试文件'), then looped three identical failures into STUCK. The
  criterion is now rebuilt from problem-statement keywords and searches
  SOURCE files; when no usable criterion can be built the step fails
  honestly with an 'unverifiable' reason and never counts as a repeated
  identical failure.
- pallets__flask-4992: apply_edit rejected an anchor even though the
  candidate file content was shipped (capped at 400 lines). The FILE
  CONTENT ANCHOR now ships up to 2000 lines, and an anchor rejection arms
  exactly ONE repair round-trip whose instruction carries up to 3 real
  candidate anchor lines (with line numbers) from the target file.

Covers:
  (a) degenerate assertion values '.', '..', 'x' are dropped and the
      criterion is rebuilt from problem-statement keywords;
  (b) a rebuilt criterion with all-test-file targets searches SOURCE files;
  (c) an unbuildable criterion reports an honest 'unverifiable' reason and
      does NOT loop into STUCK (no repeated-failure increment);
  (d) the anchor repair instruction carries real candidate anchor lines
      with line numbers when apply_edit misses;
  (e) the deterministic no-LLM path keeps the identical report shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from craft.editor import Editor
from craft.llm import LLMClient
from craft.loop import CraftLoop, _is_degenerate_assertion_value
from craft.planner import Plan, Step, SuccessCriteria, compile_plan
from craft.spec import parse_spec_text
from providers.base import LLMMessage, LLMResponse

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

KEYWORD_SPEC = (
    "修复 Blueprint 的 url_prefix 与 route 处理\n"
    "嵌套 Blueprint 的 url_prefix 拼接错误\n"
    "验收: url_prefix 断言出现\n"
    "影响: tests/test_blueprints.py"
)


def _verify_plan(
    targets: list[str],
    value: str,
    *,
    mode: str = "deterministic",
    extra_steps: list[Step] | None = None,
) -> Plan:
    steps = list(extra_steps or [])
    steps.append(
        Step(
            id=f"s{len(steps) + 1}",
            kind="verify",
            target_files=list(targets),
            intent="机械核验断言值出现在目标文件",
            success_criteria=SuccessCriteria("grep", value),
        )
    )
    return Plan(
        task_title="verify 断言落位",
        mode=mode,
        steps=steps,
        risk_classification={
            "auth": False,
            "migration": False,
            "mq": False,
            "public_api": False,
        },
        budget_alloc={"iterations": 4, "tokens": 50_000},
    )


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; records every prompt."""

    def __init__(self, replies: list[str], *, job_id: str = "job-w114") -> None:
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
        self.calls.append({**entry, "job_id": self.job_id, "model": "fake-w114"})
        return LLMResponse(content=reply, usage=usage, model="fake-w114")


def _blueprints_repo(tmp_path: Path) -> None:
    (tmp_path / "src" / "flask").mkdir(parents=True)
    (tmp_path / "src" / "flask" / "blueprints.py").write_text(
        "_PREFIX_HANDLER = 'url_prefix'\nROUTE_TABLE = {'index': 'route'}\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_blueprints.py").write_text(
        "def test_blueprints():\n    return None\n", encoding="utf-8"
    )


# -- (a) degenerate assertion values are dropped and rebuilt -----------------


@pytest.mark.parametrize("degenerate", [".", "..", "x"])
def test_degenerate_assertion_values_dropped_and_rebuilt_from_keywords(
    tmp_path: Path, degenerate: str
) -> None:
    _blueprints_repo(tmp_path)
    spec = parse_spec_text(KEYWORD_SPEC)
    plan = _verify_plan(["tests/test_blueprints.py"], degenerate)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-degenerate",
        fix_registry={},
        exec_mode="local",
    )
    assert _is_degenerate_assertion_value(degenerate) is True
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is True
    assert result is None
    assert evidence["check"] == "grep"
    assert f"断言值 {degenerate!r} 退化" in evidence["note"]
    assert "已按问题陈述重建关键词 'url_prefix'" in evidence["note"]
    assert "命中源文件 ['src/flask/blueprints.py']" in evidence["note"]
    assert "已排除测试文件 ['tests/test_blueprints.py']" in evidence["note"]
    assert "reason" not in evidence


# -- (b) all-test-file targets search SOURCE files instead --------------------


def test_all_test_file_targets_rebuilt_criterion_searches_source_files(
    tmp_path: Path,
) -> None:
    _blueprints_repo(tmp_path)
    spec = parse_spec_text(KEYWORD_SPEC)
    # the modify step carries the real source target; the verify step's own
    # target list is all test files
    plan = _verify_plan(
        ["tests/test_blueprints.py"],
        ".",
        extra_steps=[
            Step(
                id="s1",
                kind="modify",
                target_files=["src/flask/blueprints.py"],
                intent="修复 url_prefix 处理",
                success_criteria=SuccessCriteria("compile", ""),
            )
        ],
    )
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-src-only",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[1], loop.states[1])
    assert ok is True
    assert result is None
    assert "已按问题陈述重建关键词" in evidence["note"]
    assert "src/flask/blueprints.py" in evidence["note"]
    assert "无源文件可搜索" not in evidence["note"]
    assert "reason" not in evidence


# -- (c) unbuildable criterion -> honest unverifiable, no stuck loop ----------


def test_unbuildable_criterion_reports_unverifiable_without_loop(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_blueprints.py").write_text(
        "def test_blueprints():\n    return None\n", encoding="utf-8"
    )
    # problem statement carries no usable identifier keywords
    spec = parse_spec_text("修复问题\n让东西正常工作\n验收: 无\n影响: tests/test_blueprints.py")
    plan = _verify_plan(["tests/test_blueprints.py"], ".", mode="llm")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-unverifiable",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is False
    assert result is None
    assert evidence["unverifiable"] is True
    assert "unverifiable" in evidence["reason"]
    assert "退化" in evidence["reason"]

    # keywords exist but the workspace has no source file to search
    spec2 = parse_spec_text(KEYWORD_SPEC)
    plan2 = _verify_plan(["tests/test_blueprints.py"], "x")
    loop2 = CraftLoop(
        spec2,
        plan2,
        tmp_path,
        job_id="job-unverifiable-src",
        fix_registry={},
        exec_mode="local",
    )
    ok2, evidence2, result2 = loop2._check_criteria(plan2.steps[0], loop2.states[0])
    assert ok2 is False
    assert result2 is None
    assert evidence2["unverifiable"] is True
    assert "已提取关键词" in evidence2["reason"]
    assert "无任何可搜索的源文件" in evidence2["reason"]

    # end-to-end: run() fails honestly on the FIRST check — no diagnose
    # round-trips, no repeated-failure counting, no STUCK.
    client = _ScriptedClient([])
    loop3 = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-unverifiable-run",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    report = loop3.run()
    assert report["result"] == "FAILED"
    step_report = report["steps"][0]
    assert step_report["status"] == "failed"
    assert step_report["iterations"] == 0
    assert "unverifiable" in step_report["evidence"]["reason"]
    assert report["budget_used"]["iterations"] == 0
    assert client.sent_prompts == []  # never entered the diagnose loop


# -- (d) anchor repair instruction carries real lines with line numbers -------


ANCHOR_MISS_PROPOSAL = json.dumps(
    {
        "diagnosis": "补上 return endpoint 分支",
        "edits": [
            {
                "action": "apply_edit",
                "path": "src/helpers.py",
                "old": "def url_for(endpoint) return",
                "new": "    return endpoint",
            }
        ],
    },
    ensure_ascii=False,
)

ANCHOR_HIT_PROPOSAL = json.dumps(
    {
        "diagnosis": "quote the real line",
        "edits": [
            {
                "action": "apply_edit",
                "path": "src/helpers.py",
                "old": '    return "/" + endpoint',
                "new": "    return endpoint",
            }
        ],
    },
    ensure_ascii=False,
)


def test_anchor_repair_instruction_carries_real_lines_with_line_numbers(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "helpers.py").write_text(
        "def url_for(endpoint):\n"
        '    return "/" + endpoint\n'
        "\n"
        "def send_file(path):\n"
        "    return open(path).read()\n",
        encoding="utf-8",
    )
    spec = parse_spec_text("修复 helpers\n验收: return endpoint 断言出现\n影响: src/helpers.py")
    plan = _verify_plan(["src/helpers.py"], "return endpoint", mode="llm")
    client = _ScriptedClient([ANCHOR_MISS_PROPOSAL, ANCHOR_HIT_PROPOSAL])
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-anchor-repair",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    # the rejected old string's longest identifier token guides the pick
    assert loop._anchor_candidates("src/helpers.py", "def url_for(endpoint) return") == [
        (1, "def url_for(endpoint):"),
        (2, '    return "/" + endpoint'),
    ]
    report = loop.run()
    assert report["result"] == "DONE"
    assert len(client.sent_prompts) == 2  # first miss arms exactly ONE repair
    repair_prompt = client.sent_prompts[1]
    assert "EDIT PROPOSAL SELF-CHECK" in repair_prompt
    assert "apply_edit 被拒" in repair_prompt
    assert "line 1: def url_for(endpoint):" in repair_prompt
    assert 'line 2:     return "/" + endpoint' in repair_prompt
    assert "return endpoint" in (tmp_path / "src" / "helpers.py").read_text(encoding="utf-8")


# -- (e) deterministic no-LLM path unchanged ----------------------------------


def _write_fixture_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        'def double(x):\n    return x / 2\n\n\ndef greeting(name):\n    return "hello " + name\n',
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
    """The deterministic M1 path keeps the identical report shape (W114)."""
    _write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    report = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-deterministic-w114",
        fix_registry={"test": _fix_double},
        exec_mode="local",
    ).run()
    assert report["result"] == "DONE"
    assert report["mode"] == "deterministic"
    assert set(report) == {
        "job_id",
        "mode",
        "result",
        "steps",
        "diff_stat",
        "self_verify",
        "gates",
        "budget_used",
        "audit_trail",
        "gains",
    }
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
