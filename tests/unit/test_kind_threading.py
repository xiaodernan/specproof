"""Kind threading through the craft LLM layer (W94 接线).

The provider ClientPolicy layer already routes by kind (draft | diagnose |
edit_plan → cheap; court | counterexample | accept_judge |
contract_compile → strong; unknown → strong). These tests pin the craft
side of that contract with stub providers (no network, no live LLM):

- LLMClient.chat forwards kind to providers whose chat() declares it;
- providers without a kind slot (and no **kwargs) drop it silently;
- kind omitted / kind=None keeps the exact legacy call shape;
- craft_task_to_kind maps task labels onto the router vocabulary;
- mapped evidence kinds are never cacheable;
- the planner and loop call sites pass draft / diagnose for real.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from craft.llm import CRAFT_TASK_KINDS, LLMClient, craft_task_to_kind
from craft.loop import CraftLoop
from craft.planner import compile_plan, compile_plan_llm
from craft.spec import parse_spec_text
from providers.base import LLMMessage, LLMResponse
from providers.router import CHEAP_TASK_KINDS, KNOWN_TASK_KINDS, STRONG_TASK_KINDS
from providers.semantic_cache import cacheable

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

_OPEN_CLIENTS: list[LLMClient] = []

_KIND_MISSING = object()


@pytest.fixture(autouse=True)
def _close_clients() -> Iterator[None]:
    yield
    for client in _OPEN_CLIENTS:
        client.close()
    _OPEN_CLIENTS.clear()


def _ok_response(content: str = "ok") -> LLMResponse:
    return LLMResponse(
        content=content,
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        model="stub",
    )


class SwallowProvider:
    """chat(**kwargs): records whether kind was passed (no network)."""

    def __init__(self, reply: LLMResponse | None = None) -> None:
        self.reply = reply or _ok_response()
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages: list[Any], **kwargs: Any) -> LLMResponse:
        del messages
        kind = kwargs.get("kind", _KIND_MISSING)
        self.calls.append(
            {"kind": kwargs.get("kind"), "kind_passed": kind is not _KIND_MISSING}
        )
        return self.reply

    def get_capabilities(self) -> dict[str, bool]:
        return {"chat": True}


class OpenAIShapeProvider:
    """chat() with the OpenAICompatibleProvider signature (kind last)."""

    def __init__(self, reply: LLMResponse) -> None:
        self.reply = reply
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
        kind: str | None = None,
    ) -> LLMResponse:
        del messages, tools, tool_choice, opts
        self.calls.append(
            {
                "kind": kind,
                "thinking": thinking,
                "response_format": response_format,
                "timeout": timeout,
            }
        )
        return self.reply

    def get_capabilities(self) -> dict[str, bool]:
        return {"chat": True}


class LegacyProvider:
    """chat() with no kind slot and no **kwargs (pre-W94 provider shape)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[Any],
        *,
        response_format: dict[str, Any] | None = None,
        thinking: bool | dict[str, Any] = False,
        timeout: float = 180.0,
    ) -> LLMResponse:
        del messages
        self.calls.append(
            {"thinking": thinking, "response_format": response_format, "timeout": timeout}
        )
        return _ok_response()

    def get_capabilities(self) -> dict[str, bool]:
        return {"chat": True}


# -- kind propagation through LLMClient.chat -------------------------------


async def test_kind_propagates_to_provider_chat() -> None:
    provider = SwallowProvider()
    client = LLMClient(provider=provider)
    await client.chat([LLMMessage(role="user", content="hi")], label="plan", kind="draft")
    assert provider.calls[0]["kind_passed"] is True
    assert provider.calls[0]["kind"] == "draft"


async def test_kind_propagates_to_openai_shape_provider() -> None:
    provider = OpenAIShapeProvider(_ok_response())
    client = LLMClient(provider=provider)
    await client.chat(
        [LLMMessage(role="user", content="hi")], label="court", kind="court"
    )
    assert provider.calls[0]["kind"] == "court"


async def test_kind_none_default_keeps_legacy_shape() -> None:
    provider = SwallowProvider()
    client = LLMClient(provider=provider)
    await client.chat([LLMMessage(role="user", content="hi")], label="plan")
    await client.chat([LLMMessage(role="user", content="hi")], label="plan", kind=None)
    assert [call["kind_passed"] for call in provider.calls] == [False, False]


async def test_kind_dropped_for_providers_without_kind_slot() -> None:
    provider = LegacyProvider()
    client = LLMClient(provider=provider)
    response = await client.chat(
        [LLMMessage(role="user", content="hi")], label="plan", kind="draft"
    )
    assert response.content == "ok"
    assert provider.calls == [
        {"thinking": False, "response_format": None, "timeout": 180.0}
    ]


# -- mapping table ----------------------------------------------------------


def test_mapping_table() -> None:
    assert craft_task_to_kind("plan") == "draft"
    assert craft_task_to_kind("diagnose") == "diagnose"
    assert craft_task_to_kind("edit") == "edit_plan"
    assert craft_task_to_kind("judge") == "court"
    assert craft_task_to_kind("court") == "court"
    assert craft_task_to_kind("contract") == "contract_compile"
    assert craft_task_to_kind("counterexample") == "counterexample"
    assert craft_task_to_kind("unknown") is None
    assert craft_task_to_kind("") is None
    assert craft_task_to_kind(" PLAN ") == "draft"  # case/space-insensitive
    assert craft_task_to_kind("Court") == "court"


def test_every_mapped_kind_is_known_to_the_router() -> None:
    assert set(CRAFT_TASK_KINDS.values()) <= KNOWN_TASK_KINDS
    cheap = {CRAFT_TASK_KINDS[label] for label in ("plan", "diagnose", "edit")}
    strong = {
        CRAFT_TASK_KINDS[label]
        for label in ("judge", "court", "contract", "counterexample")
    }
    assert cheap <= CHEAP_TASK_KINDS
    assert strong <= STRONG_TASK_KINDS


def test_evidence_kinds_never_cacheable() -> None:
    for label in ("judge", "court", "contract", "counterexample"):
        kind = craft_task_to_kind(label)
        assert kind is not None
        assert kind in STRONG_TASK_KINDS
        assert not cacheable(kind)
    draft_kind = craft_task_to_kind("plan")
    diagnose_kind = craft_task_to_kind("diagnose")
    assert draft_kind is not None and cacheable(draft_kind)
    assert diagnose_kind is not None and cacheable(diagnose_kind)
    edit_kind = craft_task_to_kind("edit")
    assert edit_kind == "edit_plan" and not cacheable(edit_kind)


# -- call sites: planner (draft) + loop (diagnose) --------------------------


def good_plan_json() -> str:
    return json.dumps(
        {
            "steps": [
                {
                    "id": "s1",
                    "kind": "understand",
                    "target_files": ["calc.py"],
                    "intent": "x",
                    "success_criteria": {"type": "grep", "value": ""},
                    "deps": [],
                },
                {
                    "id": "s2",
                    "kind": "modify",
                    "target_files": ["calc.py"],
                    "intent": "x",
                    "success_criteria": {"type": "compile", "value": ""},
                    "deps": ["s1"],
                },
                {
                    "id": "s3",
                    "kind": "test",
                    "target_files": [],
                    "intent": "x",
                    "success_criteria": {"type": "test_green", "value": ""},
                    "deps": ["s2"],
                },
                {
                    "id": "s4",
                    "kind": "verify",
                    "target_files": [],
                    "intent": "x",
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


def diagnose_json() -> str:
    return json.dumps(
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


def test_planner_planning_passes_draft_kind() -> None:
    provider = OpenAIShapeProvider(_ok_response(good_plan_json()))
    client = LLMClient(provider=provider)
    _OPEN_CLIENTS.append(client)
    plan = compile_plan_llm(parse_spec_text(FIX_SPEC), client=client)
    assert plan.mode == "llm"
    assert provider.calls[0]["kind"] == "draft"


def test_loop_diagnosis_passes_diagnose_kind(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    provider = OpenAIShapeProvider(_ok_response(diagnose_json()))
    client = LLMClient(provider=provider)
    _OPEN_CLIENTS.append(client)
    loop = CraftLoop(
        parse_spec_text(FIX_SPEC),
        compile_plan(parse_spec_text(FIX_SPEC)),
        tmp_path,
        job_id="job-kind",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    report = loop.run()
    assert report["result"] == "DONE"
    assert provider.calls[0]["kind"] == "diagnose"
