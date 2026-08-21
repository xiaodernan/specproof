"""W143 offline regression tests — no network, no Docker, no real LLM.

Real SWE-bench LLM run evidence (docs/eval/swebench-llm-results-v6.json):

- pallets__flask-4045 STUCK s1 understand: '目标文件不可读:
  flask/blueprints.py (文件不存在: flask/blueprints.py)' — candidate paths
  mentioned in the diagnose reply were taken verbatim, but the real file
  is src/flask/blueprints.py (repo slug flask, source root src/flask).
  Mentioned paths now resolve by SUFFIX: exactly one real non-test
  workspace file ending with the mentioned path resolves to it; zero or
  multiple keep the honest failure naming the candidates found.
- pallets__flask-4992 STUCK s2 understand: "断言值 'from_file' 无源文件
  可搜索: 目标 ['tests/test_config.py'] 均为测试文件" — the understand
  stage now runs the same criterion-rebuild path as verify (degenerate/
  short values dropped, keywords rebuilt from the problem statement,
  source-only candidate files via the extended union); an unbuildable
  criterion stays an honest 'unverifiable' failure with no stuck
  increment.

Covers:
  (a) 'flask/blueprints.py' resolves to src/flask/blueprints.py when
      unique (helper + understand-stage grep read + candidate union);
  (b) ambiguous/absent suffix keeps an honest failure naming the
      candidates found;
  (c) an understand-stage criterion with a degenerate value is rebuilt to
      a source-only keyword search (scripted loop, offline);
  (d) an understand-stage criterion whose targets are all test files is
      rebuilt the same way (flask-4992 'from_file'), and an unbuildable
      one fails unverifiable without looping;
  (e) the diagnose-context anchor reads the suffix-resolved file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from craft.llm import LLMClient
from craft.loop import CraftLoop, _resolve_mentioned_path
from craft.planner import Plan, Step, SuccessCriteria
from craft.spec import TaskSpec
from providers.base import LLMMessage, LLMResponse


def _spec(title: str, description: str = "") -> TaskSpec:
    return TaskSpec(
        title=title,
        description=description,
        acceptance_criteria=[],
        forbidden_changes=[],
        affected_area_hint="",
    )


def _from_file_spec() -> TaskSpec:
    """flask-4992-style spec: the first HIT keyword in extraction order is
    'from_file', so the rebuilt criterion is deterministic."""
    return TaskSpec(
        title="flask.Config.from_file 增加 file mode 参数",
        description="Python 3.11 引入 tomllib 读取 TOML 配置",
        acceptance_criteria=["from_file 断言出现"],
        forbidden_changes=[],
        affected_area_hint="",
    )


def _grep_plan(
    kind: str,
    targets: list[str],
    value: str,
    *,
    mode: str = "deterministic",
) -> Plan:
    return Plan(
        task_title="understand 判据落位",
        mode=mode,
        steps=[
            Step(
                id="s1",
                kind=kind,
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
        budget_alloc={"iterations": 4, "tokens": 50_000},
    )


def _flask4045_repo(tmp_path: Path) -> None:
    (tmp_path / "src" / "flask").mkdir(parents=True)
    (tmp_path / "src" / "flask" / "blueprints.py").write_text(
        "BLUEPRINT_DOT_CHECK = True\n", encoding="utf-8"
    )


def _flask4992_repo(tmp_path: Path) -> None:
    (tmp_path / "src" / "flask").mkdir(parents=True)
    (tmp_path / "src" / "flask" / "config.py").write_text(
        "def from_file(self, filename, mode):\n    return mode\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_config.py").write_text(
        "def test_config():\n    return None\n", encoding="utf-8"
    )


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; records every prompt."""

    def __init__(self, replies: list[str], *, job_id: str = "job-w143") -> None:
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
        self.calls.append({**entry, "job_id": self.job_id, "model": "fake-w143"})
        return LLMResponse(content=reply, usage=usage, model="fake-w143")


# -- (a) mentioned suffix resolves when unique --------------------------------


def test_mentioned_suffix_resolves_to_unique_workspace_file() -> None:
    files = ["src/flask/blueprints.py"]
    assert _resolve_mentioned_path("flask/blueprints.py", files) == (
        "src/flask/blueprints.py",
        [],
    )
    # Windows separators normalize before matching
    assert _resolve_mentioned_path("flask\\blueprints.py", files) == (
        "src/flask/blueprints.py",
        [],
    )
    # an as-is match wins without any suffix guessing
    assert _resolve_mentioned_path("src/flask/blueprints.py", files) == (
        "src/flask/blueprints.py",
        [],
    )


def test_understand_grep_reads_suffix_resolved_file(tmp_path: Path) -> None:
    """flask-4045 s1: target 'flask/blueprints.py' reads src/flask/blueprints.py."""
    _flask4045_repo(tmp_path)
    spec = _spec("Raise error when blueprint name contains a dot")
    plan = _grep_plan("understand", ["flask/blueprints.py"], "BLUEPRINT_DOT_CHECK")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-suffix-read",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is True
    assert result is None
    assert evidence["check"] == "grep"
    assert "src/flask/blueprints.py" in evidence["note"]
    assert "reason" not in evidence


def test_candidate_union_resolves_unique_suffix_reference(tmp_path: Path) -> None:
    """The candidate-file union resolves a diagnose-mentioned suffix the same way."""
    _flask4045_repo(tmp_path)
    spec = _spec("Raise error when blueprint name contains a dot")
    plan = _grep_plan("understand", ["tests/test_blueprints.py"], ".")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-union-suffix",
        fix_registry={},
        exec_mode="local",
    )
    loop._last_diagnosis = "根因在 flask/blueprints.py 的注册逻辑"
    candidates = loop._candidate_source_files()
    assert "src/flask/blueprints.py" in candidates
    assert "flask/blueprints.py" not in candidates


def test_candidate_union_ambiguous_or_absent_suffix_adds_nothing() -> None:
    files = ["src/flask/blueprints.py", "vendor/flask/blueprints.py"]
    assert _resolve_mentioned_path("flask/blueprints.py", files) == (
        None,
        files,
    )
    assert _resolve_mentioned_path("flask/app.py", files) == (None, [])


# -- (b) ambiguous/absent suffix keeps an honest failure ----------------------


def test_ambiguous_suffix_keeps_honest_failure_listing_candidates(
    tmp_path: Path,
) -> None:
    for part in ("src", "vendor"):
        (tmp_path / part / "flask").mkdir(parents=True)
        (tmp_path / part / "flask" / "blueprints.py").write_text(
            "X = 1\n", encoding="utf-8"
        )
    spec = _spec("Raise error when blueprint name contains a dot")
    plan = _grep_plan("understand", ["flask/blueprints.py"], "BLUEPRINT_DOT_CHECK")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-suffix-ambiguous",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is False
    assert result is None
    assert "目标文件不可读" in evidence["reason"]
    assert "后缀匹配不唯一" in evidence["reason"]
    assert "src/flask/blueprints.py" in evidence["reason"]
    assert "vendor/flask/blueprints.py" in evidence["reason"]


def test_absent_suffix_keeps_honest_failure_without_fabrication(
    tmp_path: Path,
) -> None:
    _flask4045_repo(tmp_path)
    spec = _spec("Raise error when blueprint name contains a dot")
    plan = _grep_plan("understand", ["flask/app.py"], "BLUEPRINT_DOT_CHECK")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-suffix-absent",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is False
    assert result is None
    assert "文件不存在: flask/app.py" in evidence["reason"]
    assert "后缀匹配不唯一" not in evidence["reason"]


# -- (c) understand-stage degenerate value rebuilt to source-only search ------


@pytest.mark.parametrize("degenerate", [".", "..", "x"])
def test_understand_stage_degenerate_value_rebuilt_to_source_only_search(
    tmp_path: Path, degenerate: str
) -> None:
    """Scripted loop, offline: an understand-stage degenerate criterion is
    rebuilt from problem-statement keywords and searches source files only."""
    _flask4992_repo(tmp_path)
    spec = _from_file_spec()
    plan = _grep_plan("understand", ["tests/test_config.py"], degenerate)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-understand-degenerate",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is True
    assert result is None
    assert f"断言值 {degenerate!r} 退化" in evidence["note"]
    assert "已按问题陈述重建关键词 'from_file'" in evidence["note"]
    assert "命中源文件 ['src/flask/config.py']" in evidence["note"]
    assert "已排除测试文件 ['tests/test_config.py']" in evidence["note"]

    # the full offline run greens on the FIRST check — no fix, no LLM
    loop2 = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-understand-degenerate-run",
        fix_registry={},
        exec_mode="local",
    )
    report = loop2.run()
    assert report["result"] == "DONE"
    step_report = report["steps"][0]
    assert step_report["status"] == "green"
    assert step_report["iterations"] == 0
    assert "已按问题陈述重建关键词 'from_file'" in step_report["evidence"]["note"]
    assert report["budget_used"]["iterations"] == 0


# -- (d) test-only targets rebuild like verify; unbuildable stays unverifiable -


def test_understand_stage_test_only_criterion_rebuilt_like_verify(
    tmp_path: Path,
) -> None:
    """flask-4992 s2: non-degenerate 'from_file' on test-only targets runs the
    same rebuild path as verify instead of looping three times into STUCK."""
    _flask4992_repo(tmp_path)
    spec = _from_file_spec()
    plan = _grep_plan("understand", ["tests/test_config.py"], "from_file")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-understand-test-only",
        fix_registry={},
        exec_mode="local",
    )
    ok, evidence, result = loop._check_criteria(plan.steps[0], loop.states[0])
    assert ok is True
    assert result is None
    assert "断言值 'from_file' 无源文件可搜索 (目标均为测试文件)" in evidence["note"]
    assert "已按问题陈述重建关键词 'from_file'" in evidence["note"]
    assert "命中源文件 ['src/flask/config.py']" in evidence["note"]
    assert "已排除测试文件 ['tests/test_config.py']" in evidence["note"]


def test_unbuildable_test_only_criterion_unverifiable_without_loop(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_config.py").write_text(
        "def test_config():\n    return None\n", encoding="utf-8"
    )
    # the problem statement carries no usable identifier keywords
    spec = _spec("让东西正常工作")
    plan = _grep_plan("understand", ["tests/test_config.py"], "from_file", mode="llm")
    client = _ScriptedClient([])
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-unbuildable-test-only",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    report = loop.run()
    assert report["result"] == "FAILED"
    step_report = report["steps"][0]
    assert step_report["status"] == "failed"
    assert step_report["iterations"] == 0
    assert step_report["evidence"]["unverifiable"] is True
    assert "均为测试文件" in step_report["evidence"]["reason"]
    assert report["budget_used"]["iterations"] == 0
    assert client.sent_prompts == []  # never entered the diagnose loop


# -- (e) diagnose-context anchor reads the suffix-resolved file ---------------


def test_diagnose_context_reads_suffix_resolved_anchor(tmp_path: Path) -> None:
    _flask4045_repo(tmp_path)
    spec = _spec("Raise error when blueprint name contains a dot")
    plan = _grep_plan("understand", ["flask/blueprints.py"], "BLUEPRINT_DOT_CHECK")
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-anchor-suffix",
        fix_registry={},
        exec_mode="local",
    )
    context = loop._diagnose_context(plan.steps[0], None, "目标文件不可读")
    assert "--- src/flask/blueprints.py ---" in context["target_files"]
    assert "BLUEPRINT_DOT_CHECK = True" in context["target_files"]
    assert "<不可读>" not in context["target_files"]
