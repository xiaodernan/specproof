"""Responses integration uses SDK wire stubs; no credentials or network."""
import json
from types import SimpleNamespace

import pytest

from providers.base import LLMMessage
from providers.capability_probe import CapabilityProbe
from providers.openai_compatible import OpenAICompatibleProvider
from providers.responses_protocol import parse_response, request_kwargs


def completed(text="SPEC_OK", output=None):
    return {
        "status": "completed", "model": "gpt-6-astra",
        "output": output if output is not None else [{
            "type": "message", "content": [{"type": "output_text", "text": text}],
        }],
        "usage": {
            "input_tokens": 10, "output_tokens": 4, "total_tokens": 14,
            "input_tokens_details": {"cached_tokens": 3},
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    }


class Stream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    async def __aiter__(self):
        for event in self.events:
            yield event

    async def close(self):
        self.closed = True


def provider_with(outcome):
    provider = OpenAICompatibleProvider(
        base_url="https://gateway.test", api_key="test-key", model="gpt-6-astra",
        reasoning_effort="max", protocol="responses", max_retries=0,
    )
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return outcome

    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    return provider, calls


async def test_responses_uses_requested_model_effort_and_no_legacy_probes():
    provider, calls = provider_with(completed())
    response = await provider.chat([LLMMessage("user", "Check connection")])
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-6-astra"
    assert calls[0]["reasoning"] == {"effort": "max"}
    assert calls[0]["store"] is False
    assert "temperature" not in calls[0]
    assert response.content == "SPEC_OK"
    assert response.usage == {
        "prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14,
        "prompt_cache_hit_tokens": 3, "prompt_cache_miss_tokens": 7, "reasoning_tokens": 2,
    }
    assert provider.get_capabilities()["chat"]
    assert "tool_calls" not in provider.get_capabilities()
    assert "streaming" not in provider.get_capabilities()


def test_function_round_trip_and_json_schema_translation():
    call = {"id": "call-a", "function": {"name": "read_file", "arguments": '{"path":"a"}'}}
    tools = [{"type": "function", "function": {
        "name": "read_file", "parameters": {"type": "object", "properties": {}},
    }}]
    result = request_kwargs(
        "gpt-6-astra", [LLMMessage("assistant", tool_calls=[call]),
                        LLMMessage("tool", "file contents", tool_call_id="call-a")],
        effort="max", tools=tools, tool_choice="required",
        response_format={"type": "json_schema", "json_schema": {
            "name": "report", "strict": True, "schema": {"type": "object"},
        }},
    )
    assert result["input"] == [
        {"type": "function_call", "call_id": "call-a", "name": "read_file",
         "arguments": '{"path":"a"}'},
        {"type": "function_call_output", "call_id": "call-a", "output": "file contents"},
    ]
    assert result["tools"][0]["name"] == "read_file"
    assert result["tools"][0]["strict"] is False
    assert "function" not in result["tools"][0]
    assert result["text"]["format"]["schema"] == {"type": "object"}
    assert "strict" not in tools[0]["function"]


async def test_actual_text_deltas_are_not_replayed_at_completion():
    stream = Stream([
        {"type": "response.output_text.delta", "delta": "SPEC_"},
        {"type": "response.output_text.delta", "delta": "OK"},
        {"type": "response.completed", "response": completed()},
    ])
    provider, _ = provider_with(stream)
    pieces = [piece async for piece in provider.chat_stream([LLMMessage("user", "hello")])]
    assert [piece.content for piece in pieces] == ["SPEC_", "OK", None]
    assert pieces[-1].usage["total_tokens"] == 14
    assert pieces[-1].finish_reason == "stop"
    assert stream.closed
    assert provider.get_capabilities()["streaming"]


async def test_function_call_stream_outputs_complete_arguments_once():
    item = {"type": "function_call", "call_id": "call-a", "name": "read_file",
            "arguments": '{"path":"README.md"}'}
    stream = Stream([
        {"type": "response.function_call_arguments.delta", "delta": '{"path":'},
        {"type": "response.output_item.done", "item": item},
        {"type": "response.completed", "response": completed(output=[item])},
    ])
    provider, _ = provider_with(stream)
    pieces = [piece async for piece in provider.chat_stream([LLMMessage("user", "read it")])]
    calls = [call for piece in pieces for call in piece.tool_calls]
    assert len(calls) == 1
    assert calls[0]["id"] == "call-a"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "README.md"}


@pytest.mark.parametrize("events", [
    [], [{"type": "response.failed"}], [{"type": "response.incomplete"}],
    [{"type": "error"}], [{"type": "response.output_text.delta", "delta": "partial"}],
])
async def test_stream_failure_or_truncation_never_looks_successful(events):
    stream = Stream(events)
    provider, _ = provider_with(stream)
    with pytest.raises(RuntimeError):
        _ = [piece async for piece in provider.chat_stream([LLMMessage("user", "hi")])]
    assert stream.closed


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled", "in_progress"])
def test_non_completed_response_is_rejected(status):
    with pytest.raises(RuntimeError):
        parse_response({**completed(), "status": status})


async def test_single_streamed_probe_only_records_observed_capabilities():
    stream = Stream([
        {"type": "response.output_text.delta", "delta": "SPEC_OK"},
        {"type": "response.completed", "response": completed()},
    ])
    provider, calls = provider_with(stream)
    probe = await provider.run_probe()
    assert len(calls) == 1
    assert calls[0]["stream"] is True
    assert probe.capabilities["streaming"] is True
    assert "tool_calls" not in probe.capabilities
    assert "json_output" not in probe.capabilities


@pytest.mark.parametrize("url", ["https://gateway.test", "https://gateway.test/v1/"])
def test_probe_and_sdk_normalize_the_same_v1_url(url):
    probe = CapabilityProbe(url, "test", "legacy-model")
    assert probe.base_url == "https://gateway.test/v1"


def test_legacy_explicit_model_does_not_inherit_saved_responses(monkeypatch):
    monkeypatch.setattr("providers.config.load_model_config", lambda: {
        "base_url": "https://gateway.test/v1", "api_key": "test", "model": "gpt-6-astra",
        "protocol": "responses", "reasoning_effort": "max",
    })
    assert OpenAICompatibleProvider(model="deepseek-v4-pro").protocol == "chat"
    current = OpenAICompatibleProvider()
    assert current.protocol == "responses"
    assert current.reasoning_effort == "max"


def test_legacy_environment_model_does_not_inherit_saved_responses(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.delenv("LLM_PROTOCOL", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr("providers.config.load_model_config", lambda: {
        "base_url": "https://gateway.test/v1", "api_key": "test", "model": "deepseek-v4-pro",
        "protocol": "responses", "reasoning_effort": "max",
    })
    provider = OpenAICompatibleProvider()
    assert provider.protocol == "chat"
    assert provider.reasoning_effort is None


async def test_json_mode_capability_requires_parseable_output():
    provider, _ = provider_with(completed('{"ok":true}'))
    await provider.chat(
        [LLMMessage("user", "Return JSON")], response_format={"type": "json_object"},
    )
    assert provider.get_capabilities()["json_output"]


def test_responses_options_translate_token_budget_and_drop_chat_only_controls():
    kwargs = request_kwargs(
        "gpt-6-astra", [LLMMessage("user", "hello")], effort="max",
        opts={"max_tokens": 100, "temperature": 0.2, "top_p": 0.9, "thinking": True},
    )
    assert kwargs["extra_body"] == {"max_output_tokens": 100}
