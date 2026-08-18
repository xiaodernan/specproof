"""M2 LLM wiring tests — craft/llm.py + planner/loop LLM paths.

Wire-level stub provider (mirrors tests/unit/test_providers_dsv4.py): no
network, canned LLMResponse replay, chat kwargs recorded so the prompt /
thinking / response_format contract is testable.

Covered: plan JSON parse success + fallback on parse/schema/cycle/cap
failures; budget gate (check + record overruns); no-key fallback; the
diagnose-fix loop converging through Editor (uniqueness still enforced);
illegal model output -> honest FAILED; reasoning_content never reaching
checkpoint.json / report.json (ADR-017); thinking policy (plan_only keeps
diagnose thinking-off); 429 retries bounded at the provider layer.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from craft.llm import LLMClient
from craft.loop import CraftLoop
from craft.planner import compile_plan, compile_plan_llm
from craft.spec import parse_spec_text
from providers.base import LLMMessage, LLMResponse
from providers.budget import BudgetExceeded

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

REASONING_MARK = "TOP-SECRET-PRIVATE-CHAIN"

_OPEN_CLIENTS: list[LLMClient] = []


@pytest.fixture(autouse=True)
def _close_clients() -> Iterator[None]:
    yield
    for client in _OPEN_CLIENTS:
        client.close()
    _OPEN_CLIENTS.clear()


def make_client(
    outcomes: list[Any], *, token_budget: int | None = None
) -> tuple[LLMClient, StubProvider]:
    provider = StubProvider(outcomes)
    client = LLMClient(provider=provider, token_budget=token_budget)
    _OPEN_CLIENTS.append(client)
    return client, provider


def make_response(
    content: str,
    reasoning: str | None = REASONING_MARK,
    usage: dict[str, Any] | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        reasoning_content=reasoning,
        usage=usage
        if usage is not None
        else {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 40,
            "reasoning_tokens": 12,
        },
        model="deepseek-v4-pro",
    )


class StubProvider:
    """Replays canned outcomes; records chat kwargs per call (no network)."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        thinking: bool | dict[str, Any] = False,
        opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "response_format": response_format,
                "thinking": thinking,
                "opts": opts,
                "timeout": timeout,
            }
        )
        outcome = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def chat_stream(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
        thinking: bool | dict[str, Any] = False,
        opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> Any:
        raise NotImplementedError

    def get_capabilities(self) -> dict[str, bool]:
        return {"chat": True, "json_output": True, "thinking": True}


def make_spec() -> Any:
    return parse_spec_text(FIX_SPEC)


def good_plan_json() -> str:
    return json.dumps(
        {
            "steps": [
                {
                    "id": "s1",
                    "kind": "understand",
                    "target_files": ["calc.py"],
                    "intent": "阅读 calc.py 与测试约定",
                    "success_criteria": {"type": "grep", "value": ""},
                    "deps": [],
                },
                {
                    "id": "s2",
                    "kind": "modify",
                    "target_files": ["calc.py"],
                    "intent": "把 double() 的除法改为乘法",
                    "success_criteria": {"type": "compile", "value": ""},
                    "deps": ["s1"],
                },
                {
                    "id": "s3",
                    "kind": "test",
                    "target_files": [],
                    "intent": "运行 pytest 验证 test_double",
                    "success_criteria": {"type": "test_green", "value": ""},
                    "deps": ["s2"],
                },
                {
                    "id": "s4",
                    "kind": "verify",
                    "target_files": [],
                    "intent": "机械核验测试全绿",
                    "success_criteria": {"type": "test_green", "value": ""},
                    "deps": ["s3"],
                },
            ],
            "risk_classification": {
                "auth": False,
                "migration": False,
                "mq": False,
                "public_api": False,
            },
        },
        ensure_ascii=False,
    )


def diagnose_json(old: str = "return x / 2", new: str = "return x * 2") -> str:
    return json.dumps(
        {
            "diagnosis": "double() 把乘法写成了除法, 翻转操作符即可",
            "edits": [{"action": "apply_edit", "path": "calc.py", "old": old, "new": new}],
        },
        ensure_ascii=False,
    )


def write_fixture_repo(tmp_path: Path) -> None:
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


# ── planning through LLMClient ─────────────────────────────────────


def test_llm_plan_success_parses_and_validates() -> None:
    client, provider = make_client([make_response(good_plan_json())])
    plan = compile_plan_llm(make_spec(), client=client)
    assert plan.mode == "llm"
    assert plan.llm_fallback_reason == ""
    assert [step.kind for step in plan.steps] == [
        "understand",
        "modify",
        "test",
        "verify",
    ]
    assert plan.steps[1].target_files == ["calc.py"]
    call = provider.calls[0]
    assert call["thinking"] is True  # plan tier under default plan_only
    assert call["response_format"] == {"type": "json_object"}
    prompt = call["messages"][0].content
    assert "You are SpecProof" in prompt
    assert "JSON" in prompt


def test_llm_plan_unparseable_falls_back_to_deterministic() -> None:
    client, _provider = make_client([make_response("抱歉, 我无法制定计划")])
    plan = compile_plan_llm(make_spec(), client=client)
    assert plan.mode == "deterministic"
    assert "解析" in plan.llm_fallback_reason


def test_llm_plan_schema_invalid_falls_back() -> None:
    data = json.loads(good_plan_json())
    data["steps"][0]["kind"] = "teleport"
    client, _provider = make_client([make_response(json.dumps(data, ensure_ascii=False))])
    plan = compile_plan_llm(make_spec(), client=client)
    assert plan.mode == "deterministic"
    assert "校验" in plan.llm_fallback_reason


def test_llm_plan_dependency_cycle_falls_back() -> None:
    data = json.loads(good_plan_json())
    data["steps"][1]["deps"] = ["s3"]
    client, _provider = make_client([make_response(json.dumps(data, ensure_ascii=False))])
    plan = compile_plan_llm(make_spec(), client=client)
    assert plan.mode == "deterministic"
    assert "依赖" in plan.llm_fallback_reason


def test_llm_plan_step_cap_falls_back() -> None:
    data = json.loads(good_plan_json())
    data["steps"] = [
        {
            "id": f"s{i}",
            "kind": "understand",
            "target_files": [],
            "intent": "x",
            "success_criteria": {"type": "grep", "value": ""},
            "deps": [],
        }
        for i in range(1, 14)
    ]
    client, _provider = make_client([make_response(json.dumps(data, ensure_ascii=False))])
    plan = compile_plan_llm(make_spec(), client=client)
    assert plan.mode == "deterministic"
    assert "12" in plan.llm_fallback_reason


def test_llm_plan_without_key_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    plan = compile_plan(make_spec(), mode="llm")
    assert plan.mode == "deterministic"
    assert "LLM unavailable" in plan.llm_fallback_reason


def test_llm_plan_precall_budget_overrun_falls_back() -> None:
    client, provider = make_client([make_response(good_plan_json())], token_budget=5)
    plan = compile_plan_llm(make_spec(), client=client)
    assert plan.mode == "deterministic"
    assert "预算" in plan.llm_fallback_reason
    assert provider.calls == []  # the gate fired BEFORE any model call


def test_llm_plan_postcall_budget_overrun_falls_back() -> None:
    # limit sits above the estimated prompt charge (the pre-call gate
    # passes) but below the actual usage (the post-call record overruns).
    usage = {
        "prompt_tokens": 5000,
        "completion_tokens": 100,
        "total_tokens": 5100,
        "reasoning_tokens": 50,
    }
    client, provider = make_client(
        [make_response(good_plan_json(), usage=usage)], token_budget=5000
    )
    plan = compile_plan_llm(make_spec(), client=client)
    assert plan.mode == "deterministic"
    assert "预算" in plan.llm_fallback_reason
    assert len(provider.calls) == 1  # overrun recorded, never silently swallowed
    overrun = client.budget.entries[-1]
    assert overrun["prompt_tokens"] == 5000
    assert overrun["remaining_after"] < 0


def test_postcall_record_overrun_raises_and_keeps_evidence() -> None:
    client, provider = make_client(
        [make_response("ok", usage={"prompt_tokens": 1000, "completion_tokens": 100})],
        token_budget=50,
    )
    with pytest.raises(BudgetExceeded):
        client.chat_sync(
            [LLMMessage(role="user", content="hi")],
            label="t",
            estimated_prompt_tokens=1,
        )
    assert len(provider.calls) == 1
    assert client.budget.entries[-1]["prompt_tokens"] == 1000


# ── diagnose-fix loop through LLMClient ────────────────────────────


def run_llm_loop(
    tmp_path: Path, outcomes: list[Any], *, token_budget: int | None = None
) -> tuple[CraftLoop, LLMClient, dict[str, Any]]:
    write_fixture_repo(tmp_path)
    spec = make_spec()
    plan = compile_plan(spec)
    client, _provider = make_client(outcomes, token_budget=token_budget)
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-llm", fix_registry={}, exec_mode="local",
        client=client,
    )
    return loop, client, loop.run()


def test_loop_llm_fix_converges_done(tmp_path: Path) -> None:
    loop, client, report = run_llm_loop(tmp_path, [make_response(diagnose_json())])
    assert report["result"] == "DONE"
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
    steps = {step["id"]: step for step in report["steps"]}
    assert steps["s3"]["status"] == "green"
    assert steps["s3"]["iterations"] == 1
    assert report["budget_used"]["tokens"] > 0
    usage = report["llm_usage"]
    assert usage["calls"] == 1
    assert usage["reasoning_tokens"] == 12
    assert client.calls[0]["label"] == "diagnose:s3"
    assert client.calls[0]["step_id"] == "s3"
    assert client.calls[0]["job_id"] == loop.job_id
    checkpoint = json.loads(
        (loop.artifact_dir / "checkpoint.json").read_text(encoding="utf-8")
    )
    s3_entries = [e for e in checkpoint["entries"] if e["step_id"] == "s3"]
    assert s3_entries[0]["verdict"] == "green"
    assert "[LLM 诊断]" in s3_entries[0]["diagnosis"]
    assert s3_entries[0]["edits_applied"] == ["calc.py"]


def test_loop_llm_illegal_output_fails_honestly(tmp_path: Path) -> None:
    _loop, _client, report = run_llm_loop(tmp_path, [make_response("not json at all")])
    assert report["result"] == "FAILED"
    steps = {step["id"]: step for step in report["steps"]}
    assert steps["s3"]["status"] == "failed"
    assert "非法" in steps["s3"]["evidence"]["reason"]
    assert "return x / 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


def test_loop_llm_non_unique_edit_fails_and_writes_nothing(tmp_path: Path) -> None:
    _loop, _client, report = run_llm_loop(
        tmp_path, [make_response(diagnose_json(old="return"))]
    )
    assert report["result"] == "FAILED"
    steps = {step["id"]: step for step in report["steps"]}
    assert "被拒" in steps["s3"]["evidence"]["reason"]
    assert "return x / 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


def test_loop_llm_budget_overrun_fails(tmp_path: Path) -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100}
    _loop, _client, report = run_llm_loop(
        tmp_path, [make_response(diagnose_json(), usage=usage)], token_budget=50
    )
    assert report["result"] == "FAILED"
    steps = {step["id"]: step for step in report["steps"]}
    assert "预算" in steps["s3"]["evidence"]["reason"]


def test_reasoning_never_reaches_artifacts(tmp_path: Path) -> None:
    loop, client, report = run_llm_loop(tmp_path, [make_response(diagnose_json())])
    assert report["result"] == "DONE"
    assert any(entry["reasoning_content"] == REASONING_MARK for entry in client.reasoning_journal)
    for artifact in loop.artifact_dir.rglob("*"):
        if artifact.is_file():
            text = artifact.read_text(encoding="utf-8", errors="ignore")
            assert REASONING_MARK not in text, f"reasoning leaked into {artifact}"
    dumped = json.dumps(report, ensure_ascii=False)
    assert "reasoning_content" not in dumped
    assert report["llm_usage"]["reasoning_journal_entries"] == 1


def test_diagnose_thinking_off_under_plan_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_THINKING_MODE", "plan_only")
    write_fixture_repo(tmp_path)
    spec = make_spec()
    plan = compile_plan(spec)
    provider = StubProvider([make_response(diagnose_json())])
    client = LLMClient(provider=provider)
    _OPEN_CLIENTS.append(client)
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-think", fix_registry={},
        exec_mode="local", client=client,
    )
    report = loop.run()
    assert report["result"] == "DONE"
    assert provider.calls[0]["thinking"] is False


def test_diagnose_thinking_on_under_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_THINKING_MODE", "auto")
    write_fixture_repo(tmp_path)
    spec = make_spec()
    plan = compile_plan(spec)
    provider = StubProvider([make_response(diagnose_json())])
    client = LLMClient(provider=provider)
    _OPEN_CLIENTS.append(client)
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-think-auto", fix_registry={},
        exec_mode="local", client=client,
    )
    report = loop.run()
    assert report["result"] == "DONE"
    assert provider.calls[0]["thinking"] is True
