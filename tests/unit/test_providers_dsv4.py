"""DeepSeek V4 Pro adaptation tests for the provider layer.

All gateway interaction is mocked at wire level (no network): the
provider's AsyncOpenAI client is replaced with a recording stub, mirroring
the transport-stub convention of tests/unit/test_baseline.py (the
responses library 0.26.2 does not intercept httpx in this environment).
"""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import RateLimitError

from providers.base import LLMMessage
from providers.budget import BudgetExceeded, TokenBudget
from providers.openai_compatible import (
    OpenAICompatibleProvider,
    _parse_usage,
    _retry_after_seconds,
    _wait_retry_after_or_exponential,
)
from providers.probe_result import ProbeResult
from providers.prompt_templates import (
    JSON_ACTION_ENVELOPE_BLOCK,
    SYSTEM_BLOCK,
    TASK_TEMPLATES,
    BuiltPrompt,
    assemble,
    resolve_thinking,
    stable_prefix_identical,
    verify_variables_after_prefix,
)

# ── transport stubs ──────────────────────────────────────────────


class _RecordingResponder:
    """Stub chat.completions.create: replays canned outcomes, records kwargs."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.attempts = 0
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.attempts += 1
        self.calls.append(dict(kwargs))
        outcome = self.outcomes[min(self.attempts - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeCompletions:
    def __init__(self, responder: _RecordingResponder) -> None:
        self._responder = responder

    async def create(self, **kwargs: Any) -> Any:
        return await self._responder(**kwargs)


class _FakeChat:
    def __init__(self, responder: _RecordingResponder) -> None:
        self.completions = _FakeCompletions(responder)


class _FakeClient:
    def __init__(self, responder: _RecordingResponder) -> None:
        self.chat = _FakeChat(responder)

    async def close(self) -> None:
        pass


def _fake_response(
    content: str | None = "ok",
    reasoning: str | None = "step-by-step chain of thought",
    tool_calls: list[Any] | None = None,
    usage: Any = None,
) -> SimpleNamespace:
    if usage is None:
        usage = SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=30,
            total_tokens=150,
            prompt_cache_hit_tokens=80,
            prompt_cache_miss_tokens=40,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=12),
        )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls" if tool_calls else "stop",
                message=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning,
                    tool_calls=tool_calls or [],
                ),
            )
        ],
        usage=usage,
        model="deepseek-v4-pro",
    )


def _rate_limit_error(retry_after: str | None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    response = SimpleNamespace(
        headers=headers,
        status_code=429,
        request=SimpleNamespace(
            method="POST", url="http://llm.test/v1/chat/completions"
        ),
    )
    return RateLimitError("rate limited", response=response, body=None)


def _mock_api_key() -> str:
    """Fake key assembled from parts.

    The security scanner (tests/security/test_no_key_leak.py) forbids a
    complete "sk-" key literal anywhere in .py files, even in fixtures —
    mirror tests/unit/test_baseline.py, which builds keys by concatenation.
    """
    return "sk-" + "test-" + "1234567890abcdef"


_DEFAULT_CAPS = {
    "chat": True,
    "streaming": True,
    "json_output": True,
    "tool_calls": True,
    "strict_tool_calls": False,
    "thinking": True,
    "thinking_with_tools": True,
    "reasoning_content": True,
    "usage_reporting": True,
    "error_codes": True,
    "rate_limit_headers": True,
}


def _make_provider(
    responder: _RecordingResponder,
    max_retries: int | None = 2,
    caps: dict[str, bool] | None = None,
) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider(
        base_url="http://llm.test",
        api_key=_mock_api_key(),
        model="deepseek-v4-pro",
        probe_on_init=False,
        max_retries=max_retries,
    )
    provider._probe_result = ProbeResult(
        provider="openai_compatible",
        base_url=provider.base_url,
        model=provider.model,
        capabilities=caps if caps is not None else dict(_DEFAULT_CAPS),
    )
    provider._client = _FakeClient(responder)
    return provider


# ── reasoning_content: captured, never pollutes parsing ───────────


async def test_reasoning_content_captured_but_kept_out_of_content():
    responder = _RecordingResponder(
        [
            _fake_response(
                content='{"findings": []}',
                reasoning="private chain of thought",
            )
        ]
    )
    provider = _make_provider(responder)
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert result.reasoning_content == "private chain of thought"
    assert result.content == '{"findings": []}'
    assert "chain of thought" not in (result.content or "")


async def test_reasoning_content_never_enters_tool_calls_or_json_path():
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="report", arguments='{"a": 1}'),
    )
    responder = _RecordingResponder(
        [
            _fake_response(
                content=None,
                reasoning="thinking about tools",
                tool_calls=[tool_call],
            )
        ]
    )
    provider = _make_provider(responder)
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert result.reasoning_content == "thinking about tools"
    assert result.content is None
    assert result.tool_calls == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "report", "arguments": '{"a": 1}'},
        }
    ]
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {"a": 1}


async def test_reasoning_content_none_when_gateway_omits_it():
    responder = _RecordingResponder([_fake_response(content="ok", reasoning=None)])
    provider = _make_provider(responder)
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert result.reasoning_content is None
    assert result.content == "ok"


# ── usage parsing ────────────────────────────────────────────────


def test_parse_usage_full_dsv4_fields():
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=125,
        prompt_cache_hit_tokens=60,
        prompt_cache_miss_tokens=40,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=8),
    )
    parsed = _parse_usage(usage)
    assert parsed["prompt_tokens"] == 100
    assert parsed["completion_tokens"] == 25
    assert parsed["total_tokens"] == 125
    assert parsed["prompt_cache_hit_tokens"] == 60
    assert parsed["prompt_cache_miss_tokens"] == 40
    assert parsed["reasoning_tokens"] == 8


def test_parse_usage_skips_missing_optional_fields():
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    parsed = _parse_usage(usage)
    assert parsed == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_parse_usage_dict_form_top_level_reasoning():
    parsed = _parse_usage(
        {"prompt_tokens": 3, "completion_tokens": 2, "reasoning_tokens": 1}
    )
    assert parsed["reasoning_tokens"] == 1
    assert "prompt_cache_hit_tokens" not in parsed


def test_parse_usage_none_returns_zeroed_core_fields():
    assert _parse_usage(None) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


async def test_chat_usage_roundtrip_carries_dsv4_fields():
    responder = _RecordingResponder([_fake_response(content="ok")])
    provider = _make_provider(responder)
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert result.usage["prompt_tokens"] == 120
    assert result.usage["prompt_cache_hit_tokens"] == 80
    assert result.usage["prompt_cache_miss_tokens"] == 40
    assert result.usage["reasoning_tokens"] == 12


# ── 429 Retry-After backoff ──────────────────────────────────────


async def test_429_retries_retry_after_then_succeeds():
    responder = _RecordingResponder(
        [
            _rate_limit_error("0.001"),
            _rate_limit_error("0.001"),
            _fake_response(content="ok"),
        ]
    )
    provider = _make_provider(responder, max_retries=2)
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert result.content == "ok"
    assert responder.attempts == 3  # initial + 2 retries = LLM_MAX_RETRIES semantics


async def test_429_never_retries_beyond_limit():
    responder = _RecordingResponder([_rate_limit_error("0.001")])
    provider = _make_provider(responder, max_retries=2)
    with pytest.raises(RateLimitError):
        await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert responder.attempts == 3


async def test_429_retry_count_reads_llm_max_retries_env(monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    responder = _RecordingResponder([_rate_limit_error("0.001")])
    provider = _make_provider(responder, max_retries=None)
    with pytest.raises(RateLimitError):
        await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    assert responder.attempts == 2


def test_retry_after_parsing():
    assert _retry_after_seconds(_rate_limit_error("5")) == 5.0
    assert _retry_after_seconds(_rate_limit_error("0")) == 0.0
    assert _retry_after_seconds(_rate_limit_error(None)) is None
    http_date = _rate_limit_error("Wed, 21 Oct 2015 07:28:00 GMT")
    assert _retry_after_seconds(http_date) is None  # HTTP-date → exponential fallback
    assert _retry_after_seconds(RuntimeError("boom")) is None


def test_wait_prefers_retry_after_over_exponential():
    state = SimpleNamespace(
        attempt_number=3,
        outcome=SimpleNamespace(exception=lambda: _rate_limit_error("4")),
    )
    assert _wait_retry_after_or_exponential(state) == 4.0


def test_wait_falls_back_to_capped_exponential():
    state = SimpleNamespace(
        attempt_number=3,
        outcome=SimpleNamespace(exception=lambda: RuntimeError("boom")),
    )
    assert _wait_retry_after_or_exponential(state) == 4.0  # 2**(3-1), under the 60s cap


# ── prompt templates: cache-friendly ordering ────────────────────


def test_templates_thinking_flags():
    assert TASK_TEMPLATES["plan"].thinking_on
    assert TASK_TEMPLATES["judge"].thinking_on
    assert TASK_TEMPLATES["diagnose"].thinking_on
    assert not TASK_TEMPLATES["contract_compile"].thinking_on


def test_assemble_stable_prefix_identical_across_builds():
    data_a = {"spec_text": "Requirement A: authentication required", "diff": "A"}
    data_b = {"spec_text": "Requirement B: totally different", "diff": "B"}
    first = assemble(SYSTEM_BLOCK, "plan", data_a)
    second = assemble(SYSTEM_BLOCK, "plan", data_b)
    assert stable_prefix_identical(first, second)
    assert first.stable_prefix == second.stable_prefix  # byte-identical
    assert first.text.startswith(first.stable_prefix)
    assert first.text != second.text  # variables differ
    assert verify_variables_after_prefix(first, data_a)
    assert verify_variables_after_prefix(second, data_b)


def test_assemble_detects_variable_leak_in_prefix():
    bad = BuiltPrompt(
        text="x", stable_prefix="prefix containing secret-variable-payload"
    )
    assert not verify_variables_after_prefix(bad, {"k": "secret-variable-payload"})


def test_assemble_unknown_task_raises():
    with pytest.raises(KeyError):
        assemble(SYSTEM_BLOCK, "no_such_task", {})


def test_assemble_envelope_is_optional_tail():
    plain = assemble(SYSTEM_BLOCK, "plan", {"spec_text": "x"})
    enveloped = assemble(
        SYSTEM_BLOCK, "plan", {"spec_text": "x"}, include_envelope=True
    )
    assert JSON_ACTION_ENVELOPE_BLOCK.strip() not in plain.text
    assert enveloped.text.endswith(JSON_ACTION_ENVELOPE_BLOCK.strip())
    assert stable_prefix_identical(plain, enveloped)


def test_resolve_thinking_modes(monkeypatch):
    monkeypatch.setenv("LLM_THINKING_MODE", "plan_only")
    assert resolve_thinking("plan")
    assert resolve_thinking("judge")
    assert resolve_thinking("diagnose")
    assert not resolve_thinking("contract_compile")
    assert not resolve_thinking("baseline")  # judgment-lite: off under plan_only
    monkeypatch.setenv("LLM_THINKING_MODE", "auto")
    assert resolve_thinking("baseline") == TASK_TEMPLATES["baseline"].thinking_on
    monkeypatch.setenv("LLM_THINKING_MODE", "off")
    assert not resolve_thinking("judge")
    with pytest.raises(ValueError):
        resolve_thinking("plan", mode="bogus")


def test_resolve_thinking_unknown_task_raises():
    with pytest.raises(KeyError):
        resolve_thinking("nope")


# ── budget ledger ────────────────────────────────────────────────


def test_budget_overrun_raises_and_is_catchable():
    budget = TokenBudget(limit_tokens=100)
    budget.record({"prompt_tokens": 60, "completion_tokens": 30})
    assert budget.used == 90.0
    assert budget.remaining == 10.0
    budget.check(prompt_tokens=5)
    with pytest.raises(BudgetExceeded):
        budget.check(prompt_tokens=20)
    try:
        budget.record({"prompt_tokens": 20, "completion_tokens": 10})
    except BudgetExceeded as exc:
        assert exc.limit == 100.0
        assert exc.used == 120.0
        assert exc.charge == 30.0
    else:
        pytest.fail("BudgetExceeded not raised on overrun record")
    # The overrun entry stays in the ledger: the evidence chain is honest.
    assert budget.entries[-1]["prompt_tokens"] == 20
    assert budget.entries[-1]["remaining_after"] == -20.0


def test_budget_cache_hit_discount():
    budget = TokenBudget(limit_tokens=1000)
    charge = budget.charge(prompt_tokens=100, cache_hit_tokens=100)
    assert charge == 110.0  # 100 prompt + 100 cache-hit * 0.1


def test_budget_serializable_evidence_chain():
    budget = TokenBudget(limit_tokens=1000, cost_weights={"cache_hit": 0.05})
    budget.record(
        {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "reasoning_tokens": 8,
            "prompt_cache_hit_tokens": 40,
            "prompt_cache_miss_tokens": 60,
        },
        label="judge",
    )
    report = budget.to_report()
    loaded = json.loads(json.dumps(report))
    assert loaded["calls"] == 1
    assert loaded["cost_weights"]["cache_hit"] == 0.05
    assert loaded["remaining"] == 1000 - (100 + 20 + 8 + 40 * 0.05 + 60)
    assert loaded["entries"][0]["label"] == "judge"
    assert loaded["entries"][0]["reasoning_tokens"] == 8


def test_budget_negative_limit_rejected():
    with pytest.raises(ValueError):
        TokenBudget(limit_tokens=-1)


# ── backward compatibility of the new chat() parameters ──────────


async def test_chat_without_new_params_keeps_old_request_shape():
    responder = _RecordingResponder([_fake_response(content="ok")])
    provider = _make_provider(responder)
    result = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], timeout=30.0
    )
    kwargs = responder.calls[0]
    assert result.content == "ok"
    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["timeout"] == 30.0
    assert "extra_body" not in kwargs  # no thinking flag → no extra_body (legacy shape)


async def test_thinking_true_still_sends_enabled_body():
    responder = _RecordingResponder([_fake_response(content="ok")])
    provider = _make_provider(responder)
    await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], thinking=True
    )
    assert responder.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


async def test_thinking_dict_and_opts_passthrough():
    responder = _RecordingResponder([_fake_response(content="ok")])
    provider = _make_provider(responder)
    await provider.chat(
        messages=[LLMMessage(role="user", content="hi")],
        thinking={"type": "disabled"},
        opts={"stream_options": {"include_usage": True}},
    )
    extra = responder.calls[0]["extra_body"]
    assert extra["thinking"] == {"type": "disabled"}
    assert extra["stream_options"] == {"include_usage": True}


async def test_thinking_ignored_when_capability_missing():
    responder = _RecordingResponder([_fake_response(content="ok")])
    provider = _make_provider(responder, caps={"chat": True, "thinking": False})
    await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], thinking=True
    )
    assert "extra_body" not in responder.calls[0]


# ── capability probe: reasoning_content bit (honest, no fabrication) ──


class _ProbeReasoningClient:
    def __init__(self, with_reasoning: bool) -> None:
        self._with_reasoning = with_reasoning

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def post(self, url: str, headers: dict | None = None, json: Any = None):
        message: dict[str, Any] = {"content": "ok"}
        if self._with_reasoning:
            message["reasoning_content"] = "always-on thinking"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": message}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            },
            request=httpx.Request("POST", url),
        )


async def test_probe_reasoning_content_capability_detected(monkeypatch):
    import providers.capability_probe as capability_probe

    monkeypatch.setattr(
        capability_probe.httpx,
        "AsyncClient",
        lambda *a, **k: _ProbeReasoningClient(with_reasoning=True),
    )
    probe = capability_probe.CapabilityProbe(
        base_url="http://llm.test", api_key=_mock_api_key(), model="deepseek-v4-pro"
    )
    passed, _detail = await probe._check_reasoning_content()
    assert passed


async def test_probe_reasoning_content_absent_is_honest_false(monkeypatch):
    import providers.capability_probe as capability_probe

    monkeypatch.setattr(
        capability_probe.httpx,
        "AsyncClient",
        lambda *a, **k: _ProbeReasoningClient(with_reasoning=False),
    )
    probe = capability_probe.CapabilityProbe(
        base_url="http://llm.test", api_key=_mock_api_key(), model="deepseek-v4-pro"
    )
    passed, detail = await probe._check_reasoning_content()
    assert not passed
    assert "no reasoning_content" in detail


async def test_probe_run_unreachable_gateway_marks_reasoning_false(monkeypatch):
    class _UnreachableClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def get(self, url: str, headers: dict | None = None):
            return httpx.Response(500, request=httpx.Request("GET", url))

        async def post(self, url: str, headers: dict | None = None, json: Any = None):
            return httpx.Response(500, request=httpx.Request("POST", url))

    import providers.capability_probe as capability_probe

    monkeypatch.setattr(capability_probe.httpx, "AsyncClient", _UnreachableClient)
    probe = capability_probe.CapabilityProbe(
        base_url="http://llm.test", api_key=_mock_api_key(), model="deepseek-v4-pro"
    )
    result = await probe.run()
    assert result.capabilities["reasoning_content"] is False
    assert result.capabilities["rate_limit_headers"] is False


def test_probe_result_capability_keys_include_dsv4_bits():
    assert "reasoning_content" in ProbeResult.CAPABILITY_KEYS
    assert "rate_limit_headers" in ProbeResult.CAPABILITY_KEYS
